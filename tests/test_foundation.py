"""Tests for the cross-cutting foundation: audit log, users + roles,
period close, void workflow, graduated PAYE."""
from __future__ import annotations

from datetime import date, timedelta

import pytest


# ---- audit log -----------------------------------------------------------


def test_audit_record_creates_row(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.audit import record, list_recent
    from bizclinik_erp.models.audit import AuditAction

    with get_session() as s:
        row = record(s, action=AuditAction.LOGIN, entity_type="user",
                     entity_id=1, description="Test login",
                     username="testuser", payload={"ip": "127.0.0.1"})
        assert row.id is not None
        assert row.payload() == {"ip": "127.0.0.1"}

    with get_session() as s:
        rows = list_recent(s, limit=10)
        assert len(rows) >= 1
        assert any(r.username == "testuser" and r.action == AuditAction.LOGIN for r in rows)


# ---- users + roles -------------------------------------------------------


def test_create_user_and_authenticate(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.users import (
        create_user, authenticate, verify_password, hash_password,
    )
    from bizclinik_erp.models.users import Role

    with get_session() as s:
        u = create_user(s, username="alice", password="secret123",
                         role=Role.ACCOUNTANT, email="alice@example.com")
        assert u.role == Role.ACCOUNTANT

    # Wrong password fails
    with get_session() as s:
        sess = authenticate(s, "alice", "wrong")
        assert sess is None

    # Right password returns a session
    with get_session() as s:
        sess = authenticate(s, "alice", "secret123")
        assert sess is not None
        assert sess.user.username == "alice"


def test_password_hash_unique_each_time(fresh_db):
    from bizclinik_erp.services.users import hash_password, verify_password
    h1 = hash_password("hello")
    h2 = hash_password("hello")
    assert h1 != h2
    assert verify_password("hello", h1)
    assert verify_password("hello", h2)
    assert not verify_password("Hello", h1)


def test_lockout_after_5_failures(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.users import create_user, authenticate
    from bizclinik_erp.models.users import Role
    with get_session() as s:
        create_user(s, username="bob", password="ok", role=Role.SALES)
    for _ in range(5):
        with get_session() as s:
            assert authenticate(s, "bob", "wrong") is None
    # On the 6th attempt, even with the correct password the account is locked.
    with get_session() as s:
        assert authenticate(s, "bob", "ok") is None


def test_role_permissions():
    from bizclinik_erp.models.users import PERMISSIONS, Role
    assert "manage.users" in PERMISSIONS[Role.ADMIN]
    assert "manage.users" not in PERMISSIONS[Role.SALES]
    assert "post.invoice" in PERMISSIONS[Role.SALES]
    assert "post.bill" not in PERMISSIONS[Role.SALES]
    assert "view.reports" in PERMISSIONS[Role.VIEWER]


# ---- fiscal period close -------------------------------------------------


def test_post_in_open_period(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import post_journal, JELine
    from bizclinik_erp.models import Account
    from sqlalchemy import select

    with get_session() as s:
        bank = s.execute(select(Account).where(Account.code == '1120')).scalar_one()
        cap = s.execute(select(Account).where(Account.code == '3100')).scalar_one()
        je = post_journal(s, date(2026, 3, 15), 'Capital',
                          [JELine(account_id=bank.id, debit=1000),
                           JELine(account_id=cap.id, credit=1000)])
        assert je.is_balanced


def test_post_blocked_in_closed_period(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import post_journal, JELine
    from bizclinik_erp.services.fiscal import close_period, PeriodClosedError
    from bizclinik_erp.models import Account
    from sqlalchemy import select

    with get_session() as s:
        close_period(s, 2026, 1)

    with get_session() as s:
        bank = s.execute(select(Account).where(Account.code == '1120')).scalar_one()
        cap = s.execute(select(Account).where(Account.code == '3100')).scalar_one()
        with pytest.raises(PeriodClosedError):
            post_journal(s, date(2026, 1, 15), 'Late entry',
                          [JELine(account_id=bank.id, debit=500),
                           JELine(account_id=cap.id, credit=500)])


def test_admin_override_posts_into_closed_period(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import post_journal, JELine
    from bizclinik_erp.services.fiscal import close_period
    from bizclinik_erp.models import Account
    from sqlalchemy import select

    with get_session() as s:
        close_period(s, 2026, 1)
        bank = s.execute(select(Account).where(Account.code == '1120')).scalar_one()
        cap = s.execute(select(Account).where(Account.code == '3100')).scalar_one()
        je = post_journal(s, date(2026, 1, 15), 'Admin override',
                          [JELine(account_id=bank.id, debit=500),
                           JELine(account_id=cap.id, credit=500)],
                          allow_closed_period=True)
        assert je.is_balanced


def test_locked_period_blocks_even_admin(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import post_journal, JELine
    from bizclinik_erp.services.fiscal import lock_period, PeriodClosedError
    from bizclinik_erp.models import Account
    from sqlalchemy import select

    with get_session() as s:
        lock_period(s, 2026, 1)

    with get_session() as s:
        bank = s.execute(select(Account).where(Account.code == '1120')).scalar_one()
        cap = s.execute(select(Account).where(Account.code == '3100')).scalar_one()
        with pytest.raises(PeriodClosedError):
            post_journal(s, date(2026, 1, 15), 'Override attempt',
                          [JELine(account_id=bank.id, debit=500),
                           JELine(account_id=cap.id, credit=500)],
                          allow_closed_period=True)


def test_reopen_period_allows_posting_again(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import post_journal, JELine
    from bizclinik_erp.services.fiscal import close_period, reopen_period
    from bizclinik_erp.models import Account
    from sqlalchemy import select

    with get_session() as s:
        close_period(s, 2026, 1)
        reopen_period(s, 2026, 1, reason="Forgot rent accrual entry")

    with get_session() as s:
        bank = s.execute(select(Account).where(Account.code == '1120')).scalar_one()
        cap = s.execute(select(Account).where(Account.code == '3100')).scalar_one()
        je = post_journal(s, date(2026, 1, 15), 'Re-opened post',
                          [JELine(account_id=bank.id, debit=500),
                           JELine(account_id=cap.id, credit=500)])
        assert je.is_balanced


# ---- void workflow -------------------------------------------------------


def _seed_customer_supplier_product(s):
    from bizclinik_erp.models import Customer, Supplier, Product
    s.add(Customer(code='C1', name='Acme'))
    s.add(Supplier(code='S1', name='Vendor'))
    s.add(Product(sku='P1', name='Widget', standard_price=1000,
                   standard_cost=600, is_stockable=True))
    s.flush()


def test_void_invoice_reverses_je_and_flips_status(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, voids
    from bizclinik_erp.models import Customer, Product, DocStatus, JournalLine, JournalEntry
    from sqlalchemy import select, func

    with get_session() as s:
        _seed_customer_supplier_product(s)

    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        inv = sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 6, 1),
            lines=[sales.LineInput(product_id=prod.id, description='Widget',
                                     qty=2, unit_price=1000, tax_rate=0.075)],
        )
        inv_id = inv.id

    with get_session() as s:
        result = voids.void_invoice(s, inv_id, reason="customer cancelled",
                                      on=date(2026, 6, 2))
        assert result["reversing_je_nos"]

    # Status flipped + TB balanced
    with get_session() as s:
        from bizclinik_erp.models import SalesInvoice
        inv = s.get(SalesInvoice, inv_id)
        assert inv.status == DocStatus.CANCELLED
        tot_dr = s.execute(select(func.coalesce(func.sum(JournalLine.debit), 0))).scalar_one()
        tot_cr = s.execute(select(func.coalesce(func.sum(JournalLine.credit), 0))).scalar_one()
        assert abs(tot_dr - tot_cr) < 0.01


def test_void_bill_reverses_je_and_flips_status(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import purchase, voids
    from bizclinik_erp.models import Supplier, Product, DocStatus, JournalLine
    from sqlalchemy import select, func

    with get_session() as s:
        _seed_customer_supplier_product(s)

    with get_session() as s:
        sup = s.execute(select(Supplier)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bill = purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=date(2026, 6, 1),
            lines=[purchase.POLineInput(product_id=prod.id, description='Widget',
                                          qty=10, unit_cost=600, tax_rate=0.075)],
        )
        bill_id = bill.id

    with get_session() as s:
        result = voids.void_bill(s, bill_id, reason="wrong qty",
                                   on=date(2026, 6, 2))
        assert result["reversing_je_nos"]

    with get_session() as s:
        from bizclinik_erp.models import Bill
        bill = s.get(Bill, bill_id)
        assert bill.status == DocStatus.CANCELLED
        tot_dr = s.execute(select(func.coalesce(func.sum(JournalLine.debit), 0))).scalar_one()
        tot_cr = s.execute(select(func.coalesce(func.sum(JournalLine.credit), 0))).scalar_one()
        assert abs(tot_dr - tot_cr) < 0.01


# ---- graduated PAYE -----------------------------------------------------


def test_paye_below_first_band():
    from bizclinik_erp.services.paye import compute_paye_annual
    # Gross 240k → after CRA (200k + 0.2*240k = 248k) + pension (8% = 19.2k)
    #   chargeable = 240k - 248k - 19.2k = -27.2k → 0 → PAYE = 0
    r = compute_paye_annual(240_000)
    assert r.paye_annual == 0


def test_paye_high_income_uses_top_band():
    from bizclinik_erp.services.paye import compute_paye_annual
    r = compute_paye_annual(10_000_000)
    # High earner: should pay across multiple bands, total > 1.4M
    assert r.paye_annual > 1_400_000
    # Top band (24%) should be hit
    assert any(rate == 0.24 for _, rate, _ in r.band_breakdown)


def test_paye_monotonic_with_gross():
    from bizclinik_erp.services.paye import compute_paye_annual
    a = compute_paye_annual(2_000_000).paye_annual
    b = compute_paye_annual(5_000_000).paye_annual
    c = compute_paye_annual(10_000_000).paye_annual
    assert a <= b <= c
