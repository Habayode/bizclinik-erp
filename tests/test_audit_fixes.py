"""Regression tests for the 2026-06 accounting audit fixes:

1. run_payroll uses graduated CITA PAYE (flat paye_rate only as explicit override)
2. over-limit recurring bills queue for approval instead of auto-posting
3. receipts/payments cannot exceed the document's outstanding balance
4. paid invoices/bills cannot be voided while live receipts/payments exist
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select


def _bank(s):
    from bizclinik_erp.models import BankAccount
    return s.execute(select(BankAccount)).scalars().first()


# --------------------------------------------------------------------------- #
# 1. Graduated PAYE                                                            #
# --------------------------------------------------------------------------- #

def test_payroll_uses_graduated_paye_by_default(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Employee
    from bizclinik_erp.services import payroll
    from bizclinik_erp.services.paye import compute_paye_monthly
    with get_session() as s:
        emp = Employee(code="EG1", name="Graduated Worker",
                       monthly_gross=250_000, paye_rate=0.0)  # no override
        s.add(emp); s.flush()
        run = payroll.run_payroll(
            s, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
            pay_date=date(2026, 6, 30),
            inputs=[payroll.PayslipInput(employee_id=emp.id)],
            bank_account_id=_bank(s).id)
        slip = run.payslips[0]
        expected = compute_paye_monthly(250_000,
                                        pension_employee_rate=0.08).paye_monthly
        assert slip.paye == pytest.approx(expected, abs=0.01)
        assert slip.paye > 0          # graduated PAYE on 250k/month is not zero


def test_payroll_flat_rate_still_honoured_as_override(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Employee
    from bizclinik_erp.services import payroll
    with get_session() as s:
        emp = Employee(code="EF1", name="Flat Worker",
                       monthly_gross=200_000, paye_rate=0.10)  # explicit flat
        s.add(emp); s.flush()
        run = payroll.run_payroll(
            s, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
            pay_date=date(2026, 6, 30),
            inputs=[payroll.PayslipInput(employee_id=emp.id)],
            bank_account_id=_bank(s).id)
        assert run.payslips[0].paye == pytest.approx(20_000, abs=0.01)


# --------------------------------------------------------------------------- #
# 2. Recurring bills respect approval limits                                   #
# --------------------------------------------------------------------------- #

def _make_bill_template(s, *, qty, unit_cost):
    from bizclinik_erp.models import (RecurringFrequency, RecurringKind,
                                      RecurringTemplate, Supplier)
    sup = Supplier(code="RSUP", name="Recurring Supplies Ltd")
    s.add(sup); s.flush()
    tpl = RecurringTemplate(
        code="RT-1", name="Monthly supplies", kind=RecurringKind.BILL,
        frequency=RecurringFrequency.MONTHLY, next_run_date=date(2026, 6, 1),
        supplier_id=sup.id, line_description="Supplies",
        qty=qty, unit_cost=unit_cost, tax_rate=0.0)
    s.add(tpl); s.flush()
    return tpl


def test_recurring_bill_over_limit_queues_for_approval(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Bill, ApprovalStatus
    from bizclinik_erp.services import recurring, approvals
    from sqlalchemy import func
    with get_session() as s:
        _make_bill_template(s, qty=1, unit_cost=645_000)   # > AP 250k limit
        out = recurring.run_due(s, as_of=date(2026, 6, 1))
        assert out["materialized"] == 1
        assert out["docs"][0].startswith("APPROVAL-")
        # No bill posted; a PENDING approval request exists instead.
        assert s.execute(select(func.count(Bill.id))).scalar() == 0
        pend = approvals.list_pending(s)
        assert len(pend) == 1 and pend[0].status == ApprovalStatus.PENDING
        # Approving it posts the bill via the standard executor.
        approvals.approve(s, pend[0].id, approver_user_id=9,
                          approver_role="ADMIN")
        assert s.execute(select(func.count(Bill.id))).scalar() == 1


def test_recurring_bill_under_limit_posts_directly(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Bill
    from bizclinik_erp.services import recurring
    from sqlalchemy import func
    with get_session() as s:
        _make_bill_template(s, qty=1, unit_cost=50_000)    # under AP limit
        out = recurring.run_due(s, as_of=date(2026, 6, 1))
        assert out["materialized"] == 1
        assert out["docs"][0].startswith("BIL-")
        assert s.execute(select(func.count(Bill.id))).scalar() == 1


# --------------------------------------------------------------------------- #
# 3. Overpayment guards                                                        #
# --------------------------------------------------------------------------- #

def _invoice(s, total=100_000):
    from bizclinik_erp.models import Customer
    from bizclinik_erp.services import sales
    cust = Customer(code="OC1", name="Overpay Customer")
    s.add(cust); s.flush()
    inv = sales.issue_invoice(
        s, customer_id=cust.id, invoice_date=date(2026, 6, 1),
        lines=[sales.LineInput(product_id=None, description="Service",
                               qty=1, unit_price=total, tax_rate=0.0)])
    return cust, inv


def test_receipt_cannot_exceed_invoice_outstanding(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales
    with get_session() as s:
        cust, inv = _invoice(s, total=100_000)
        with pytest.raises(ValueError, match="exceeds the outstanding"):
            sales.record_receipt(s, customer_id=cust.id,
                                 receipt_date=date(2026, 6, 2),
                                 amount=150_000, bank_account_id=_bank(s).id,
                                 invoice_id=inv.id)
        # Paying exactly the outstanding works.
        sales.record_receipt(s, customer_id=cust.id,
                             receipt_date=date(2026, 6, 2),
                             amount=100_000, bank_account_id=_bank(s).id,
                             invoice_id=inv.id)
        # And now even ₦1 more is rejected.
        with pytest.raises(ValueError, match="exceeds the outstanding"):
            sales.record_receipt(s, customer_id=cust.id,
                                 receipt_date=date(2026, 6, 3),
                                 amount=1, bank_account_id=_bank(s).id,
                                 invoice_id=inv.id)


def test_payment_cannot_exceed_bill_outstanding(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Account, Supplier
    from bizclinik_erp.services import purchase
    with get_session() as s:
        sup = Supplier(code="OS1", name="Overpay Supplier")
        s.add(sup); s.flush()
        exp = s.execute(select(Account).where(Account.code.like("6%"))).scalars().first()
        bill = purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=date(2026, 6, 1),
            lines=[purchase.POLineInput(product_id=None, description="Rent",
                                        qty=1, unit_cost=80_000, tax_rate=0.0,
                                        expense_account_id=exp.id)])
        with pytest.raises(ValueError, match="exceeds the outstanding"):
            purchase.record_payment(s, supplier_id=sup.id,
                                    payment_date=date(2026, 6, 2),
                                    amount=90_000, bank_account_id=_bank(s).id,
                                    bill_id=bill.id)


# --------------------------------------------------------------------------- #
# 4. Void-paid blocks                                                          #
# --------------------------------------------------------------------------- #

def test_void_paid_invoice_blocked_until_receipts_voided(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, voids
    with get_session() as s:
        cust, inv = _invoice(s, total=50_000)
        rct = sales.record_receipt(s, customer_id=cust.id,
                                   receipt_date=date(2026, 6, 2),
                                   amount=50_000, bank_account_id=_bank(s).id,
                                   invoice_id=inv.id)
        inv_id, rct_id = inv.id, rct.id
    with get_session() as s:
        with pytest.raises(ValueError, match="receipt"):
            voids.void_invoice(s, inv_id, reason="entered in error")
        # Void the receipt first, then the invoice voids cleanly.
        voids.void_receipt(s, rct_id, reason="entered in error")
        out = voids.void_invoice(s, inv_id, reason="entered in error")
        assert out["reversing_je_nos"]


def test_void_paid_bill_blocked_until_payments_voided(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Account, Supplier
    from bizclinik_erp.services import purchase, voids
    with get_session() as s:
        sup = Supplier(code="VS1", name="Void Supplier")
        s.add(sup); s.flush()
        exp = s.execute(select(Account).where(Account.code.like("6%"))).scalars().first()
        bill = purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=date(2026, 6, 1),
            lines=[purchase.POLineInput(product_id=None, description="Rent",
                                        qty=1, unit_cost=40_000, tax_rate=0.0,
                                        expense_account_id=exp.id)])
        purchase.record_payment(s, supplier_id=sup.id,
                                payment_date=date(2026, 6, 2),
                                amount=40_000, bank_account_id=_bank(s).id,
                                bill_id=bill.id)
        bill_id = bill.id
    with get_session() as s:
        with pytest.raises(ValueError, match="payment"):
            voids.void_bill(s, bill_id, reason="entered in error")
