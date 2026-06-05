"""Statements module tests: customer SOA helpers + PDF exporters."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select


def _account_id(s, code: str) -> int:
    from bizclinik_erp.models import Account
    return s.execute(select(Account).where(Account.code == code)).scalar_one().id


def _bank_id(s, code: str = "BANK1") -> int:
    from bizclinik_erp.models import BankAccount
    return s.execute(select(BankAccount).where(BankAccount.code == code)).scalar_one().id


def _add_customer(s, code="CUST-1", name="Acme Trading Ltd"):
    from bizclinik_erp.models import Customer
    c = Customer(code=code, name=name, email="ap@acme.example",
                 address="12 Marina, Lagos", phone="+234 800 0000")
    s.add(c)
    s.flush()
    return c


def _add_supplier(s, code="SUP-1", name="Beta Supplies Ltd"):
    from bizclinik_erp.models import Supplier
    sp = Supplier(code=code, name=name, email="billing@beta.example",
                  address="5 Allen Ave, Lagos", phone="+234 802 0000")
    s.add(sp)
    s.flush()
    return sp


def _issue(s, customer_id, on, amount, *, tax_rate=0.0):
    from bizclinik_erp.services import sales as sales_svc
    return sales_svc.issue_invoice(
        s, customer_id=customer_id, invoice_date=on,
        lines=[sales_svc.LineInput(
            product_id=None, description="Consulting services",
            qty=1.0, unit_price=amount, tax_rate=tax_rate,
        )],
    )


# ---------------------------------------------------------------------------
# (a) outstanding = invoices - receipt
# ---------------------------------------------------------------------------


def test_customer_outstanding_equals_invoices_minus_receipt(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sales_svc
    from bizclinik_erp.services.customer_statement import customer_outstanding

    with get_session() as s:
        c = _add_customer(s)
        cust_id = c.id
        bank_id = _bank_id(s)

    with get_session() as s:
        _issue(s, cust_id, date(2026, 3, 1), 100_000.0)
        _issue(s, cust_id, date(2026, 3, 5), 150_000.0)
        inv3 = _issue(s, cust_id, date(2026, 3, 10), 200_000.0)
        inv3_id = inv3.id

    with get_session() as s:
        sales_svc.record_receipt(
            s, customer_id=cust_id, receipt_date=date(2026, 3, 12),
            amount=120_000.0, bank_account_id=bank_id,
            invoice_id=inv3_id,
        )

    with get_session() as s:
        bal = customer_outstanding(s, cust_id, as_of=date(2026, 3, 31))
    assert bal == pytest.approx(330_000.0, abs=0.01), (
        f"Expected 330_000 outstanding, got {bal}"
    )


# ---------------------------------------------------------------------------
# (b) ledger is chronological with monotonic running balance trajectory
# ---------------------------------------------------------------------------


def test_customer_ledger_chronological_and_running_balance(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sales_svc
    from bizclinik_erp.services.customer_statement import customer_ledger

    with get_session() as s:
        c = _add_customer(s)
        cust_id = c.id
        bank_id = _bank_id(s)

    with get_session() as s:
        _issue(s, cust_id, date(2026, 4, 1), 50_000.0)
        _issue(s, cust_id, date(2026, 4, 5), 75_000.0)
        _issue(s, cust_id, date(2026, 4, 10), 100_000.0)

    with get_session() as s:
        sales_svc.record_receipt(
            s, customer_id=cust_id, receipt_date=date(2026, 4, 15),
            amount=60_000.0, bank_account_id=bank_id,
        )

    with get_session() as s:
        rows = customer_ledger(
            s, cust_id,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
        )

    assert len(rows) == 4, f"Expected 4 ledger lines, got {len(rows)}"
    # Chronological
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates), "Ledger rows are not chronological"
    # Running balance check: starts at 50k, 125k, 225k, 165k
    expected = [50_000.0, 125_000.0, 225_000.0, 165_000.0]
    for r, e in zip(rows, expected):
        assert r["running_balance"] == pytest.approx(e, abs=0.01), (
            f"At {r['date']} expected running {e}, got {r['running_balance']}"
        )


# ---------------------------------------------------------------------------
# (c) customer statement PDF renders to a non-empty file
# ---------------------------------------------------------------------------


def test_write_customer_statement_pdf_produces_pdf(fresh_db, tmp_path):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.customer_statement_pdf import (
        write_customer_statement_pdf,
    )

    with get_session() as s:
        c = _add_customer(s)
        cust_id = c.id

    with get_session() as s:
        _issue(s, cust_id, date(2026, 5, 1), 80_000.0)
        _issue(s, cust_id, date(2026, 5, 12), 45_000.0)

    out = tmp_path / "soa.pdf"
    with get_session() as s:
        result = write_customer_statement_pdf(
            s, cust_id,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            out_path=out,
        )
    assert result == out
    assert out.exists(), "PDF was not written"
    size = out.stat().st_size
    assert size > 1000, f"PDF too small ({size} bytes) — likely empty"

    # Refuse to overwrite
    from bizclinik_erp.db import get_session as _gs
    with _gs() as s:
        with pytest.raises(FileExistsError):
            write_customer_statement_pdf(
                s, cust_id,
                period_start=date(2026, 5, 1),
                period_end=date(2026, 5, 31),
                out_path=out,
            )


# ---------------------------------------------------------------------------
# (d) WHT certificate PDF runs against a bill with WHT-rate line
# ---------------------------------------------------------------------------


def test_write_wht_certificate_pdf_with_wht_bill(fresh_db, tmp_path):
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.wht_certificate_pdf import (
        write_wht_certificate_pdf,
    )
    from bizclinik_erp.services import purchase as purchase_svc

    wht_rate = get_settings().default_wht_rate

    with get_session() as s:
        sup = _add_supplier(s)
        sup_id = sup.id

    with get_session() as s:
        purchase_svc.receive_bill(
            s, supplier_id=sup_id, bill_date=date(2026, 6, 1),
            lines=[purchase_svc.POLineInput(
                product_id=None,
                description="Professional services",
                qty=1.0, unit_cost=500_000.0,
                tax_rate=wht_rate,
                expense_account_id=_account_id(s, "6900"),
            )],
        )

    out = tmp_path / "wht.pdf"
    with get_session() as s:
        result = write_wht_certificate_pdf(
            s, sup_id,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            out_path=out,
        )
    assert result == out
    assert out.exists(), "WHT PDF was not written"
    size = out.stat().st_size
    assert size > 1000, f"PDF too small ({size} bytes) — likely empty"


def test_write_wht_certificate_pdf_empty_period_still_renders(fresh_db, tmp_path):
    """Edge: even when no WHT bills exist, the cert should still render."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.wht_certificate_pdf import (
        write_wht_certificate_pdf,
    )

    with get_session() as s:
        sup = _add_supplier(s, code="SUP-2", name="Idle Supplier")
        sup_id = sup.id

    out = tmp_path / "wht_empty.pdf"
    with get_session() as s:
        write_wht_certificate_pdf(
            s, sup_id,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            out_path=out,
        )
    assert out.exists()
    assert out.stat().st_size > 1000
