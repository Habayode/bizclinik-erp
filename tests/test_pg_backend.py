"""Backend abstraction (SQLite default, Postgres URL mapping) + copy/verify."""
from __future__ import annotations

from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# URL / dbname mapping                                                         #
# --------------------------------------------------------------------------- #

def test_default_backend_is_sqlite(monkeypatch):
    monkeypatch.delenv("BIZCLINIK_DB_BACKEND", raising=False)
    from bizclinik_erp import dbbackend
    assert dbbackend.is_sqlite() and not dbbackend.is_postgres()
    assert dbbackend.make_url("/data/bizclinik.db") == "sqlite:////data/bizclinik.db"


def test_postgres_dbname_mapping(monkeypatch):
    monkeypatch.setenv("BIZCLINIK_DB_BACKEND", "postgres")
    monkeypatch.setenv("BIZCLINIK_PG_PREFIX", "bizclinik")
    from bizclinik_erp import dbbackend
    f = dbbackend.pg_dbname_for
    assert f("/opt/app/data/bizclinik.db") == "bizclinik"
    assert f("/opt/app/data/control.db") == "bizclinik_control"
    assert f("/opt/app/data/tenants/wendysrack/bizclinik.db") == "bizclinik_t_wendysrack"
    # Windows-style path + odd slug chars are sanitised.
    assert f(r"C:\app\data\tenants\Big Co!\bizclinik.db") == "bizclinik_t_big_co"


def test_postgres_url_built(monkeypatch):
    monkeypatch.setenv("BIZCLINIK_DB_BACKEND", "postgres")
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGUSER", "bizclinik")
    monkeypatch.setenv("PGPASSWORD", "secret pw")
    from bizclinik_erp import dbbackend
    url = dbbackend.make_url("/data/bizclinik.db")
    assert url == "postgresql+psycopg://bizclinik:secret%20pw@127.0.0.1:5432/bizclinik"


# --------------------------------------------------------------------------- #
# copy_one: row-copy + count verification (SQLite -> SQLite proxy)             #
# --------------------------------------------------------------------------- #

def test_copy_one_verifies_counts(fresh_db, tmp_path):
    """Populate the source DB, copy it to a second SQLite file, and confirm the
    migration's own row-count + ledger-sum verification reports OK."""
    from datetime import date
    from bizclinik_erp.db import get_session, Base
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.services import sales, pg_migrate
    from bizclinik_erp.models import Customer, Product

    # Seed some real ledger activity in the source (the fresh_db default DB).
    with get_session() as s:
        s.add(Customer(code="C1", name="Acme"))
        s.add(Product(sku="P1", name="Widget", standard_price=100,
                      standard_cost=40, is_stockable=False))
        s.flush()
        c = s.query(Customer).first(); p = s.query(Product).first()
        sales.issue_invoice(s, customer_id=c.id, invoice_date=date(2026, 1, 10),
                            lines=[sales.LineInput(product_id=p.id, description="W",
                                                   qty=2, unit_price=100, tax_rate=0.075)])

    src_path = str(get_settings().db_path)
    dst = tmp_path / "copied.db"
    rep = pg_migrate.copy_one(src_path, Base.metadata, dst_url=f"sqlite:///{dst}")

    assert rep["ok"] is True, rep["mismatches"]
    assert rep["tables"].get("account", 0) > 0       # COA copied
    assert rep["tables"].get("journal_line", 0) > 0  # ledger copied
    assert dst.exists()


def test_copy_one_is_idempotent(fresh_db, tmp_path):
    """Re-running the copy into a populated destination clears + recopies
    cleanly (no PK collisions) and still verifies OK with identical counts."""
    from bizclinik_erp.db import Base
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.services import pg_migrate

    src_path = str(get_settings().db_path)
    dst = tmp_path / "copied2.db"
    r1 = pg_migrate.copy_one(src_path, Base.metadata, dst_url=f"sqlite:///{dst}")
    r2 = pg_migrate.copy_one(src_path, Base.metadata, dst_url=f"sqlite:///{dst}")
    assert r1["ok"] and r2["ok"]
    assert r1["tables"]["account"] == r2["tables"]["account"]
