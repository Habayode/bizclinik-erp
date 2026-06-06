"""One-time data migration: SQLite books -> PostgreSQL (database-per-tenant).

Run with ``BIZCLINIK_DB_BACKEND=postgres`` and the PG* connection env set. For
each source SQLite DB (default, control plane, every tenant) it:

  1. CREATE DATABASE <name> on the Postgres server if absent (provision),
  2. create the schema there (SQLAlchemy create_all),
  3. copy every row of every table,
  4. reset identity sequences so new inserts don't collide,
  5. verify row counts (and journal_line debit/credit sums) match.

The SQLite files are read-only here and left untouched — they remain the
instant rollback. Nothing is dropped.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, func, insert, inspect, select, text

from ..config import get_settings
from ..db import Base
from ..tenancy import ControlBase
from .. import dbbackend


def _tenants_from_sqlite(control_path: str) -> list[dict]:
    """Read tenant slug/db_path straight from the SQLite control DB (the Postgres
    control DB is empty until migrated, so we can't rely on it here)."""
    if not Path(control_path).exists():
        return []
    eng = create_engine(f"sqlite:///{control_path}")
    try:
        if not inspect(eng).has_table("tenant"):
            return []
        with eng.connect() as c:
            rows = c.execute(text("SELECT slug, db_path FROM tenant")).mappings().all()
        return [dict(r) for r in rows]
    finally:
        eng.dispose()


def source_dbs() -> list[dict]:
    """List every SQLite DB to migrate: {path, metadata, label}."""
    settings = get_settings()
    data_dir = Path(settings.db_path).parent
    control_path = str(data_dir / "control.db")

    out = [{"path": str(settings.db_path), "metadata": Base.metadata, "label": "default"}]
    if Path(control_path).exists():
        out.append({"path": control_path, "metadata": ControlBase.metadata,
                    "label": "control"})
    for t in _tenants_from_sqlite(control_path):
        if Path(t["db_path"]).exists():
            out.append({"path": t["db_path"], "metadata": Base.metadata,
                        "label": f"tenant-{t['slug']}"})
    return out


def provision_databases() -> list[str]:
    """CREATE DATABASE for each target if it doesn't exist. Returns created names."""
    if not dbbackend.is_postgres():
        raise RuntimeError("Set BIZCLINIK_DB_BACKEND=postgres before provisioning.")
    admin = create_engine(dbbackend.pg_admin_url(), isolation_level="AUTOCOMMIT",
                          future=True)
    created = []
    try:
        with admin.connect() as c:
            for src in source_dbs():
                name = dbbackend.pg_dbname_for(src["path"])
                exists = c.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"),
                    {"n": name}).scalar()
                if not exists:
                    c.execute(text(f'CREATE DATABASE "{name}"'))
                    created.append(name)
    finally:
        admin.dispose()
    return created


def ensure_database(dbname: str) -> bool:
    """CREATE DATABASE ``dbname`` if it doesn't already exist.

    Returns True if it was created, False if it already existed or the backend
    is not Postgres (SQLite auto-creates its file, so nothing to do). Used when
    a new tenant is registered at runtime so its per-tenant Postgres database
    exists before we bootstrap its schema.
    """
    if not dbbackend.is_postgres():
        return False
    admin = create_engine(dbbackend.pg_admin_url(), isolation_level="AUTOCOMMIT",
                          future=True)
    try:
        with admin.connect() as c:
            exists = c.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": dbname}).scalar()
            if exists:
                return False
            c.execute(text(f'CREATE DATABASE "{dbname}"'))
            return True
    finally:
        admin.dispose()


def _reset_sequences(dst_engine, metadata) -> None:
    """After bulk insert with explicit ids, advance each table's id sequence."""
    with dst_engine.begin() as conn:
        for table in metadata.sorted_tables:
            if "id" not in table.c:
                continue
            conn.execute(text(
                "SELECT setval(pg_get_serial_sequence(:t, 'id'), "
                "COALESCE((SELECT MAX(id) FROM \"" + table.name + "\"), 1), true)"
            ), {"t": table.name})


def copy_one(sqlite_path: str, metadata, *, dst_url: Optional[str] = None) -> dict:
    """Copy every table from a SQLite file into its target DB. Verifies counts."""
    src = create_engine(f"sqlite:///{sqlite_path}", future=True)
    dst = create_engine(dst_url or dbbackend.make_url(sqlite_path), future=True)
    is_pg = (dst_url or dbbackend.make_url(sqlite_path)).startswith("postgresql")
    report = {"tables": {}, "ok": True, "mismatches": []}
    try:
        metadata.create_all(dst)
        src_insp = inspect(src)
        with src.connect() as sconn, dst.begin() as dconn:
            # Idempotent: clear target tables (child -> parent) so a re-run
            # doesn't collide on primary keys.
            for table in reversed(metadata.sorted_tables):
                dconn.execute(table.delete())
            for table in metadata.sorted_tables:
                if not src_insp.has_table(table.name):
                    continue
                src_cols = {c["name"] for c in src_insp.get_columns(table.name)}
                cols = [c for c in table.columns if c.name in src_cols]
                rows = sconn.execute(
                    select(*[table.c[c.name] for c in cols])).mappings().all()
                if rows:
                    dconn.execute(insert(table), [dict(r) for r in rows])
                report["tables"][table.name] = len(rows)
        if is_pg:
            _reset_sequences(dst, metadata)

        # Verify row counts table-by-table.
        with src.connect() as sconn, dst.connect() as dconn:
            for tname, n in report["tables"].items():
                dn = dconn.execute(
                    select(func.count()).select_from(text(f'"{tname}"'))).scalar()
                if int(dn) != int(n):
                    report["ok"] = False
                    report["mismatches"].append(f"{tname}: src={n} dst={dn}")
            # Strong integrity check on the ledger, if present.
            if src_insp.has_table("journal_line"):
                for col in ("debit", "credit"):
                    sv = sconn.execute(text(
                        f"SELECT COALESCE(SUM({col}),0) FROM journal_line")).scalar()
                    dv = dconn.execute(text(
                        f"SELECT COALESCE(SUM({col}),0) FROM journal_line")).scalar()
                    if round(float(sv or 0), 2) != round(float(dv or 0), 2):
                        report["ok"] = False
                        report["mismatches"].append(
                            f"journal_line.{col} sum: src={sv} dst={dv}")
    finally:
        src.dispose()
        dst.dispose()
    return report


def migrate_all(*, provision: bool = True) -> dict:
    """Provision + copy every SQLite DB to Postgres. Returns a full report."""
    if not dbbackend.is_postgres():
        raise RuntimeError("Set BIZCLINIK_DB_BACKEND=postgres before migrating.")
    result = {"created": [], "databases": [], "ok": True}
    if provision:
        result["created"] = provision_databases()
    for src in source_dbs():
        rep = copy_one(src["path"], src["metadata"])
        rep["label"] = src["label"]
        rep["target"] = dbbackend.pg_dbname_for(src["path"])
        result["databases"].append(rep)
        if not rep["ok"]:
            result["ok"] = False
    return result
