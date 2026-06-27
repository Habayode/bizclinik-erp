"""Additive migration: a DB created before a column was added gets it back."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


def test_ensure_schema_adds_missing_column(monkeypatch):
    """Simulate an old DB: create sales_invoice WITHOUT currency_code, then run
    ensure_schema and confirm the column is added and queryable."""
    tmp = Path(tempfile.mkdtemp()) / "old.db"
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(tmp))

    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()

    # Hand-build an "old-schema" sales_invoice table WITHOUT the fx columns.
    eng = create_engine(f"sqlite:///{tmp}", future=True)
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE sales_invoice ("
            " id INTEGER PRIMARY KEY,"
            " number VARCHAR(32),"
            " invoice_date DATE,"
            " customer_id INTEGER,"
            " status VARCHAR(16),"
            " amount_paid FLOAT"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO sales_invoice (id, number, invoice_date, customer_id,"
            " status, amount_paid) VALUES (1, 'INV-OLD', '2026-01-01', 1,"
            " 'POSTED', 0.0)"
        ))
    eng.dispose()

    # Sanity: the column really is missing -> query would fail today.
    eng2 = create_engine(f"sqlite:///{tmp}", future=True)
    cols_before = {c[1] for c in eng2.connect().execute(
        text("PRAGMA table_info(sales_invoice)")).fetchall()}
    assert "currency_code" not in cols_before
    eng2.dispose()

    # Run the migrator via init_db (clears cache so it uses this DB).
    from bizclinik_erp.db import get_engine as ge, init_db
    ge.cache_clear()
    init_db()

    # Now the columns exist and default correctly.
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import SalesInvoice
    with get_session() as s:
        inv = s.get(SalesInvoice, 1)
        assert inv is not None
        assert inv.currency_code == "NGN"   # backfilled default
        assert inv.fx_rate == 1.0

    ge.cache_clear()
    _session_factory.cache_clear()


def test_idempotent(fresh_db):
    """ensure_schema on an already-current DB applies nothing new."""
    from bizclinik_erp.services.migrate import ensure_schema
    applied = ensure_schema()
    # No ADD COLUMN statements (everything already present).
    adds = [a for a in applied if a.startswith("ALTER")]
    assert adds == []


def test_default_literal_boolean_is_sql_literal_not_int():
    """Regression: a boolean default must render as true/false, never 1/0.
    `BOOLEAN DEFAULT 1` is rejected by Postgres and once broke login when the
    welcome_show/welcome_voice columns silently failed to migrate."""
    from sqlalchemy import Boolean, Column
    from bizclinik_erp.services.migrate import _default_literal
    assert _default_literal(Column("x", Boolean, default=True)) == "true"
    assert _default_literal(Column("y", Boolean, default=False)) == "false"


def test_ensure_schema_readds_dropped_boolean_column(fresh_db):
    """A DB predating a boolean column gets it back with no failed DDL."""
    import sqlite3
    if sqlite3.sqlite_version_info < (3, 35, 0):
        import pytest
        pytest.skip("needs SQLite >= 3.35 for ALTER TABLE DROP COLUMN")
    from sqlalchemy import inspect, text
    from bizclinik_erp.db import get_engine
    from bizclinik_erp.services.migrate import ensure_schema

    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text('ALTER TABLE "user" DROP COLUMN welcome_voice'))
    assert "welcome_voice" not in {c["name"] for c in inspect(eng).get_columns("user")}

    applied = ensure_schema(eng)
    assert not any("FAILED" in a for a in applied), applied
    assert "welcome_voice" in {c["name"] for c in inspect(eng).get_columns("user")}


def test_ensure_database_noop_on_sqlite():
    """ensure_database is a no-op (returns False) when not on Postgres."""
    from bizclinik_erp.services.pg_migrate import ensure_database
    from bizclinik_erp import dbbackend
    assert dbbackend.is_postgres() is False
    assert ensure_database("bizclinik_t_whatever") is False


def test_create_tenant_uses_ensure_database_hook():
    """Regression: create_tenant must provision the per-tenant Postgres DB.

    The live Postgres CREATE DATABASE path is exercised in production
    provisioning; here we assert the wiring exists so it can't silently
    regress — create_tenant references ensure_database + pg_dbname_for guarded
    by is_postgres()."""
    import inspect
    from bizclinik_erp import tenancy
    src = inspect.getsource(tenancy.create_tenant)
    assert "is_postgres()" in src
    assert "ensure_database" in src
    assert "pg_dbname_for" in src


def test_migrate_cli_covers_default_and_tenants(monkeypatch, tmp_path):
    """`bizclinik_erp migrate` must run init_db on the default DB AND every
    tenant DB (this is what update.sh relies on to apply new tables/columns to
    all tenants, not just the legacy default)."""
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(tmp_path / "legacy.db"))
    from sqlalchemy import inspect
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    from bizclinik_erp import tenancy, db as _db

    def _rc():
        get_settings.cache_clear(); get_engine.cache_clear(); _session_factory.cache_clear()

    _rc(); tenancy._reset_control_cache()
    from bizclinik_erp.services.bootstrap import bootstrap
    bootstrap(admin_password="x")
    tenancy.create_tenant("acme", "Acme Ltd", admin_password="pw")

    # Run the CLI command and confirm it succeeds.
    from bizclinik_erp.cli import cmd_migrate
    assert cmd_migrate(None) == 0

    # The tenant DB carries the HR tables (proves the tenant was migrated).
    _db.set_active_db_path(tenancy.get_tenant("acme")["db_path"]); _rc()
    names = set(inspect(get_engine()).get_table_names())
    assert {"hr_job_opening", "hr_candidate", "hr_leave_request"} <= names

    _db.set_active_db_path(None); _rc(); tenancy._reset_control_cache()
