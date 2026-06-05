"""Recurring transactions tests."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

# Make the repo root importable when running pytest from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def session():
    """Fresh SQLite DB seeded with defaults + one customer, supplier, product."""
    tmpdir = tempfile.mkdtemp(prefix="bizclinik_test_")
    db_path = Path(tmpdir) / "test.db"
    os.environ["BIZCLINIK_DB_PATH"] = str(db_path)

    # Bust caches so the new env path is picked up.
    from bizclinik_erp import config as cfg_mod
    from bizclinik_erp import db as db_mod
    cfg_mod.get_settings.cache_clear()
    db_mod.get_engine.cache_clear()
    db_mod._session_factory.cache_clear()

    from bizclinik_erp.db import reset_db, get_session
    from bizclinik_erp.services.seed import seed_defaults
    from bizclinik_erp.models import Customer, Product, Supplier

    reset_db()
    with get_session() as s:
        seed_defaults(s)
        s.add(Customer(code="C001", name="Acme Tenants"))
        s.add(Supplier(code="S001", name="Landlord Inc"))
        s.add(Product(sku="SUB-1", name="Monthly Subscription",
                      standard_price=5000, standard_cost=0,
                      is_stockable=False))

    with get_session() as s:
        yield s


# ---- (a) MONTHLY INVOICE template -----------------------------------------


def test_monthly_invoice_template_materialises_and_advances(session):
    from bizclinik_erp.models import (
        Customer, RecurringFrequency, RecurringKind, SalesInvoice,
    )
    from bizclinik_erp.services import recurring as rec_svc

    cust = session.execute(select(Customer)).scalar_one()
    tpl = rec_svc.create_template(
        session,
        kind=RecurringKind.INVOICE,
        code="REC-INV-1",
        name="Monthly subscription",
        frequency=RecurringFrequency.MONTHLY,
        next_run_date=date(2026, 3, 1),
        payload={
            "customer_id": cust.id,
            "line_description": "Monthly subscription",
            "qty": 1,
            "unit_price": 5000.0,
            "tax_rate": 0.075,
        },
    )
    session.commit()

    result = rec_svc.run_due(session, as_of=date(2026, 3, 2))
    assert result["materialized"] == 1
    assert result["skipped"] == 0
    assert len(result["docs"]) == 1

    invs = session.execute(select(SalesInvoice)).scalars().all()
    assert len(invs) == 1
    inv = invs[0]
    assert inv.customer_id == cust.id
    assert abs(inv.subtotal - 5000.0) < 0.01

    session.refresh(tpl)
    assert tpl.next_run_date == date(2026, 4, 1)
    assert tpl.last_run_doc == inv.number
    assert tpl.last_run_at is not None


# ---- (b) JOURNAL template (Salaries DR / Bank CR) -------------------------


def test_journal_template_posts_balanced_je(session):
    from bizclinik_erp.models import (
        Account, JournalEntry, RecurringFrequency, RecurringKind,
    )
    from bizclinik_erp.services import recurring as rec_svc

    salaries = session.execute(
        select(Account).where(Account.code == "6100")
    ).scalar_one()
    bank = session.execute(
        select(Account).where(Account.code == "1120")
    ).scalar_one()

    rec_svc.create_template(
        session,
        kind=RecurringKind.JOURNAL,
        code="REC-JE-1",
        name="Monthly salary standing order",
        frequency=RecurringFrequency.MONTHLY,
        next_run_date=date(2026, 3, 1),
        payload={
            "memo": "Standing order — salaries",
            "lines": [
                {"account_id": salaries.id, "debit": 10000, "credit": 0,
                 "memo": "Salaries"},
                {"account_id": bank.id, "debit": 0, "credit": 10000,
                 "memo": "Bank"},
            ],
        },
    )
    session.commit()

    result = rec_svc.run_due(session, as_of=date(2026, 3, 2))
    assert result["materialized"] == 1

    jes = session.execute(
        select(JournalEntry).where(JournalEntry.source_kind == "RECURRING")
    ).scalars().all()
    assert len(jes) == 1
    je = jes[0]
    assert je.is_balanced
    assert abs(je.total_debit - 10000.0) < 0.01
    assert abs(je.total_credit - 10000.0) < 0.01


# ---- (c) advance() month-end edge cases ------------------------------------


def test_advance_handles_month_end():
    from bizclinik_erp.models import RecurringFrequency
    from bizclinik_erp.services.recurring import advance

    # Jan 31 + 1 month → Feb 28 (2026 is not a leap year)
    assert advance(date(2026, 1, 31), RecurringFrequency.MONTHLY) == date(2026, 2, 28)
    # Jan 31 + 3 months → Apr 30 (April has 30 days)
    assert advance(date(2026, 1, 31), RecurringFrequency.QUARTERLY) == date(2026, 4, 30)
    # Leap year sanity: Jan 31 2024 + 1 month → Feb 29
    assert advance(date(2024, 1, 31), RecurringFrequency.MONTHLY) == date(2024, 2, 29)
    # Annual: simple add
    assert advance(date(2026, 6, 15), RecurringFrequency.ANNUAL) == date(2027, 6, 15)


# ---- (d) Inactive templates are skipped ------------------------------------


def test_inactive_templates_are_skipped(session):
    from bizclinik_erp.models import (
        Customer, RecurringFrequency, RecurringKind, SalesInvoice,
    )
    from bizclinik_erp.services import recurring as rec_svc

    cust = session.execute(select(Customer)).scalar_one()
    tpl = rec_svc.create_template(
        session,
        kind=RecurringKind.INVOICE,
        code="REC-INV-OFF",
        name="Disabled subscription",
        frequency=RecurringFrequency.MONTHLY,
        next_run_date=date(2026, 3, 1),
        payload={
            "customer_id": cust.id,
            "line_description": "Should not post",
            "qty": 1,
            "unit_price": 9999.0,
            "tax_rate": 0.0,
        },
    )
    tpl.is_active = False
    session.commit()

    due = rec_svc.due_templates(session, as_of=date(2026, 3, 31))
    assert tpl not in due

    result = rec_svc.run_due(session, as_of=date(2026, 3, 31))
    assert result["materialized"] == 0

    invs = session.execute(select(SalesInvoice)).scalars().all()
    assert len(invs) == 0

    session.refresh(tpl)
    assert tpl.next_run_date == date(2026, 3, 1)  # unchanged
