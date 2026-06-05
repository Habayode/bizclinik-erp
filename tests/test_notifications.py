"""Tests for the notifications service: overdue AR, upcoming bills, digest."""
from __future__ import annotations

from datetime import date, timedelta

import pytest


TODAY = date(2026, 6, 5)


def _seed_partners(s):
    from bizclinik_erp.models import Customer, Supplier, Product
    s.add(Customer(code="C1", name="Acme Ltd"))
    s.add(Supplier(code="S1", name="Vendor Co"))
    s.add(Product(sku="P1", name="Widget", standard_price=1000,
                  standard_cost=600, is_stockable=True))
    s.flush()


def test_overdue_invoice_detected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, notifications
    from bizclinik_erp.models import Customer
    from sqlalchemy import select

    with get_session() as s:
        _seed_partners(s)

    # Invoice due 20 days ago, no stock so no COGS issues, unpaid.
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=TODAY - timedelta(days=40),
            due_date=TODAY - timedelta(days=20),
            lines=[sales.LineInput(product_id=None, description="Service",
                                   qty=1, unit_price=5000, tax_rate=0.0)],
        )

    with get_session() as s:
        rows = notifications.overdue_invoices(s, as_of=TODAY)
        assert len(rows) == 1
        row = rows[0]
        assert row["days_overdue"] == 20
        assert row["outstanding"] == 5000.0
        assert row["customer"] == "Acme Ltd"


def test_upcoming_bill_within_window(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import purchase, notifications
    from bizclinik_erp.models import Supplier
    from sqlalchemy import select

    with get_session() as s:
        _seed_partners(s)

    # Bill due in 3 days — should fall in the 7-day window.
    with get_session() as s:
        sup = s.execute(select(Supplier)).scalar_one()
        purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=TODAY,
            due_date=TODAY + timedelta(days=3),
            lines=[purchase.POLineInput(product_id=None, description="Supplies",
                                        qty=1, unit_cost=8000, tax_rate=0.0,
                                        expense_account_id=None)],
        )

    with get_session() as s:
        rows = notifications.upcoming_bills(s, as_of=TODAY, within_days=7)
        assert len(rows) == 1
        row = rows[0]
        assert row["days_until"] == 3
        assert row["outstanding"] == 8000.0
        assert row["supplier"] == "Vendor Co"

    # A bill due in 30 days is outside the window.
    with get_session() as s:
        sup = s.execute(select(Supplier)).scalar_one()
        purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=TODAY,
            due_date=TODAY + timedelta(days=30),
            lines=[purchase.POLineInput(product_id=None, description="Future",
                                        qty=1, unit_cost=1000, tax_rate=0.0,
                                        expense_account_id=None)],
        )
    with get_session() as s:
        rows = notifications.upcoming_bills(s, as_of=TODAY, within_days=7)
        assert len(rows) == 1  # still only the 3-day bill


def test_build_digest_counts_and_totals(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, purchase, notifications
    from bizclinik_erp.models import Customer, Supplier
    from sqlalchemy import select

    with get_session() as s:
        _seed_partners(s)

    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        sup = s.execute(select(Supplier)).scalar_one()
        sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=TODAY - timedelta(days=40),
            due_date=TODAY - timedelta(days=20),
            lines=[sales.LineInput(product_id=None, description="Service",
                                   qty=1, unit_price=5000, tax_rate=0.0)],
        )
        purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=TODAY,
            due_date=TODAY + timedelta(days=3),
            lines=[purchase.POLineInput(product_id=None, description="Supplies",
                                        qty=1, unit_cost=8000, tax_rate=0.0,
                                        expense_account_id=None)],
        )

    with get_session() as s:
        digest = notifications.build_digest(s, as_of=TODAY)

    assert digest["overdue_count"] == 1
    assert digest["overdue_total"] == 5000.0
    assert digest["upcoming_count"] == 1
    assert digest["upcoming_total"] == 8000.0
    assert "generated_at" in digest
    assert set(digest["items"]) == {
        "overdue_invoices", "upcoming_bills", "low_stock", "cash_position",
    }


def test_render_digest_text_mentions_overdue(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, notifications
    from bizclinik_erp.models import Customer
    from sqlalchemy import select

    with get_session() as s:
        _seed_partners(s)

    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=TODAY - timedelta(days=40),
            due_date=TODAY - timedelta(days=20),
            lines=[sales.LineInput(product_id=None, description="Service",
                                   qty=1, unit_price=5000, tax_rate=0.0)],
        )

    with get_session() as s:
        digest = notifications.build_digest(s, as_of=TODAY)

    text = notifications.render_digest_text(digest)
    assert text.strip()
    assert "Overdue invoices: 1" in text
    # HTML renderer also produces non-empty branded output.
    html = notifications.render_digest_html(digest)
    assert "BizClinik ERP" in html and "#1F3864" in html
