"""STAGED migration: convert money columns from float8 to NUMERIC(18,2) on
Postgres. NOT run automatically — invoke deliberately during a maintenance
window, AFTER a backup, and it verifies each database's trial balance is
unchanged (to the kobo) before committing.

Why: float8 storage is the one remaining accounting hazard flagged in the
audit. The application-layer Decimal summation (bizclinik_erp.money.msum) already
removes accumulation drift; this makes the *storage* exact too, so SQL
aggregations (func.sum) are exact NUMERIC and there is no sub-cent loophole.

Scope: Postgres only. SQLite is dev/test (no true column-type change, and not
the live backend), so this is a no-op there.

Usage (per database, deliberate):
    # 1. Back up first (see DECIMALIZE_RUNBOOK.md): pg_dump every database.
    # 2. Dry run — list what would change, verify nothing else:
    python -m deploy.migrations.decimalize_money --all-tenants --dry-run
    # 3. Apply (transactional per DB; rolls back that DB if the trial balance moves):
    python -m deploy.migrations.decimalize_money --all-tenants

Each column is altered with `USING (col::numeric(18,2))`, which rounds any
float8 artefact to a clean 2dp value. The migration is wrapped per database in a
single transaction and aborts that database if SUM(debit)/SUM(credit) on
journal_line change by more than 0.005.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from bizclinik_erp.db import Base, get_engine
from bizclinik_erp import models as _models  # noqa: F401  register all tables on Base.metadata
from bizclinik_erp import tenancy
from bizclinik_erp.config import get_settings

# Float columns that are NOT money (quantities, rates, scores, days). Every
# other Float column in the schema is treated as money and converted.
NON_MONEY_COLUMNS = {
    # quantities
    "qty", "qty_on_hand", "qty_in", "qty_out", "qty_on_hand_after",
    "reorder_level", "annual_leave_days", "days",
    # rates / percentages — MUST NOT be rounded to 2dp (would corrupt FX & tax)
    "rate", "tax_rate", "fx_rate", "paye_rate", "pension_rate",
    "pension_employer_rate", "pension_employee_rate",
    # exam scores / non-money totals
    "ca_score", "exam_score", "total",
}


def money_columns() -> list[tuple[str, str]]:
    """Derive (table, column) money pairs from the ORM: Float columns minus the
    known non-money names. Print and eyeball this list before applying."""
    from sqlalchemy import Float
    out: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if isinstance(col.type, Float) and col.name not in NON_MONEY_COLUMNS:
                out.append((table.name, col.name))
    return out


def _tb_sums(conn) -> tuple[float, float]:
    row = conn.execute(text(
        "SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM journal_line"
    )).one()
    return round(float(row[0]), 2), round(float(row[1]), 2)


def _is_postgres(engine) -> bool:
    return engine.dialect.name == "postgresql"


def migrate_active_db(*, dry_run: bool) -> dict:
    """Convert money columns to NUMERIC(18,2) on the currently-active DB."""
    eng = get_engine()
    label = str(eng.url).rsplit("/", 1)[-1]
    if not _is_postgres(eng):
        return {"db": label, "skipped": "not postgres (dev/SQLite)"}

    cols = money_columns()
    existing = set()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public'"
        )).all()
        typ = {(t, c): d for t, c, d in rows}
        for tbl, col in cols:
            if (tbl, col) in typ:
                existing.add((tbl, col))
        todo = [(t, c) for (t, c) in cols
                if (t, c) in existing and typ[(t, c)] not in ("numeric",)]

    if dry_run:
        return {"db": label, "would_convert": len(todo), "columns": todo[:50]}

    with eng.begin() as conn:
        before = _tb_sums(conn)
        for tbl, col in todo:
            conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" '
                f'TYPE numeric(18,2) USING ("{col}"::numeric(18,2))'
            ))
        after = _tb_sums(conn)
        if abs(before[0] - after[0]) > 0.005 or abs(before[1] - after[1]) > 0.005:
            raise SystemExit(
                f"ABORT {label}: trial balance moved {before} -> {after}; rolled back.")
    return {"db": label, "converted": len(todo), "tb_before": before, "tb_after": after}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Decimalize money columns (Postgres).")
    ap.add_argument("--all-tenants", action="store_true",
                    help="Run across the default DB + every registered tenant.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change; make no changes.")
    args = ap.parse_args(argv)

    get_settings.cache_clear()
    results = []
    # default DB
    tenancy.set_active(None)
    results.append(migrate_active_db(dry_run=args.dry_run))
    if args.all_tenants:
        for t in tenancy.list_tenants():
            slug = t["slug"] if isinstance(t, dict) else t.slug
            tenancy.set_active(slug)
            r = migrate_active_db(dry_run=args.dry_run)
            r["tenant"] = slug
            results.append(r)

    for r in results:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
