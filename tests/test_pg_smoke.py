"""Postgres smoke test — exercises the REAL production backend that the
SQLite suite can't. Runs only when BIZCLINIK_DB_BACKEND=postgres (CI sets a
postgres service + the PG env); otherwise the whole module is skipped.

It proves the things that only manifest on Postgres:
  * money columns are NUMERIC (and qty/rate stay double precision) after
    create_all() — i.e. a fresh tenant gets exact money storage, no float8;
  * ORM reads of those NUMERIC columns come back as Python float (asdecimal=
    False), so there is no Decimal/float mixing in the service layer;
  * a balanced journal posts and the trial balance ties on real Postgres.
"""
from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import inspect, select

pytestmark = pytest.mark.skipif(
    (os.environ.get("BIZCLINIK_DB_BACKEND") or "").lower() != "postgres",
    reason="Postgres smoke test runs only when BIZCLINIK_DB_BACKEND=postgres",
)


@pytest.fixture
def pg_db():
    from bizclinik_erp import authz
    from bizclinik_erp import db as _db
    from bizclinik_erp import dbbackend
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.services.pg_migrate import ensure_database
    from bizclinik_erp.services.seed import seed_defaults

    get_settings.cache_clear()
    for fn in (_db.get_engine, _db._session_factory):
        try:
            fn.cache_clear()
        except Exception:
            pass
    dbname = dbbackend.pg_dbname_for(str(get_settings().db_path))
    ensure_database(dbname)      # CREATE DATABASE <prefix> if absent
    _db.reset_db()               # clean schema from the (Money-typed) models
    with _db.get_session() as s:
        seed_defaults(s)
    authz.clear_actor()
    yield


def test_money_columns_numeric_on_postgres(pg_db):
    from bizclinik_erp.db import get_engine
    insp = inspect(get_engine())

    def types(table):
        return {c["name"]: str(c["type"]).upper() for c in insp.get_columns(table)}

    jl = types("journal_line")
    assert "NUMERIC" in jl["debit"] and "NUMERIC" in jl["credit"]
    sil = types("sales_invoice_line")
    assert "NUMERIC" in sil["unit_price"] and "NUMERIC" in sil["unit_cost"]
    # quantities and rates must stay floating point, not be rounded to 2dp
    assert "NUMERIC" not in sil["qty"]
    assert "NUMERIC" not in types("tax_code")["rate"]


def test_post_reads_float_and_balances_on_postgres(pg_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Account, JournalLine
    from bizclinik_erp.services.ledger import JELine, post_journal, trial_balance

    with get_session() as s:
        ids = s.execute(
            select(Account.id).where(Account.is_postable == True).limit(2)
        ).scalars().all()
        assert len(ids) >= 2
        je = post_journal(
            s, date(2026, 1, 1), "pg smoke",
            [JELine(account_id=ids[0], debit=12345.67),
             JELine(account_id=ids[1], credit=12345.67)],
            source_kind="ADJUSTMENT",
        )
        line = s.execute(
            select(JournalLine).where(JournalLine.entry_id == je.id,
                                      JournalLine.debit > 0)
        ).scalars().first()
        # The NUMERIC column reads back as float (no Decimal leakage), correct value.
        assert type(line.debit) is float
        assert abs(line.debit - 12345.67) < 0.005
        tb = trial_balance(s)
        dr = round(sum(r["debit"] for r in tb), 2)
        cr = round(sum(r["credit"] for r in tb), 2)
        assert abs(dr - cr) < 0.01
