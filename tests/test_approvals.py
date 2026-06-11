"""Approval workflow: per-role limits, deferred-execution gate, approve/reject."""
from __future__ import annotations

from datetime import date

import pytest


def _supplier_and_expense(s):
    """Minimal master data for a bill: a supplier + an expense account id."""
    from sqlalchemy import select
    from bizclinik_erp.models import Account, Supplier
    sup = Supplier(code="SUP1", name="ACME Supplies")
    s.add(sup)
    s.flush()
    exp = s.execute(select(Account).where(Account.code.like("6%"))).scalars().first()
    return sup.id, exp.id


def _bill_payload(supplier_id, exp_acct, qty=10, unit_cost=600.0, tax=0.075):
    return {
        "supplier_id": supplier_id,
        "bill_date": "2026-06-01",
        "due_date": None,
        "currency_code": "NGN",
        "fx_rate": None,
        "notes": None,
        "lines": [{"product_id": None, "description": "Widgets", "qty": qty,
                   "unit_cost": unit_cost, "tax_rate": tax,
                   "expense_account_id": exp_acct}],
    }


def test_default_limits_and_predicates(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    with get_session() as s:
        assert approvals.role_limit(s, "ADMIN") is None            # unlimited
        assert approvals.role_limit(s, "ACCOUNTANT") == 1_000_000
        assert approvals.role_limit(s, "AP") == 250_000
        # AP can approve 250k, not 300k
        assert approvals.can_approve(s, "AP", 250_000) is True
        assert approvals.can_approve(s, "AP", 300_000) is False
        assert approvals.requires_approval(s, "AP", 300_000) is True
        assert approvals.requires_approval(s, "AP", 200_000) is False
        # Admin never needs approval and can approve anything
        assert approvals.requires_approval(s, "ADMIN", 9_999_999) is False
        assert approvals.can_approve(s, "ADMIN", 9_999_999) is True


def test_gate_under_limit_executes_immediately(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    from bizclinik_erp.models import Bill
    from sqlalchemy import select, func
    with get_session() as s:
        sup_id, exp = _supplier_and_expense(s)
        # 10 * 600 * 1.075 = 6,450 — well under AP's 250k limit
        res = approvals.gate(s, doc_type="BILL", amount=6_450.0,
                             title="Bill — ACME", payload=_bill_payload(sup_id, exp),
                             user_id=1, role="AP")
        assert res["status"] == "done"
        assert s.execute(select(func.count(Bill.id))).scalar() == 1


def test_gate_over_limit_queues_and_blocks(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    from bizclinik_erp.models import Bill, ApprovalStatus
    from sqlalchemy import select, func
    with get_session() as s:
        sup_id, exp = _supplier_and_expense(s)
        # 1000 * 600 * 1.075 = 645,000 — over AP's 250k limit
        res = approvals.gate(s, doc_type="BILL", amount=645_000.0,
                             title="Big bill — ACME",
                             payload=_bill_payload(sup_id, exp, qty=1000),
                             user_id=1, role="AP")
        assert res["status"] == "pending"
        # NOTHING posted yet — no Bill row exists
        assert s.execute(select(func.count(Bill.id))).scalar() == 0
        pend = approvals.list_pending(s)
        assert len(pend) == 1 and pend[0].status == ApprovalStatus.PENDING
        assert pend[0].amount_ngn == 645_000.0


def test_approve_executes_the_document(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    from bizclinik_erp.models import Bill
    from sqlalchemy import select, func
    with get_session() as s:
        sup_id, exp = _supplier_and_expense(s)
        res = approvals.gate(s, doc_type="BILL", amount=645_000.0, title="Big bill",
                             payload=_bill_payload(sup_id, exp, qty=1000),
                             user_id=2, role="AP")
        rid = res["request_id"]
    with get_session() as s:
        # Accountant (1m limit) approves — bill is now created + posted
        out = approvals.approve(s, rid, approver_user_id=9, approver_role="ACCOUNTANT")
        assert out["ref"]
    with get_session() as s:
        assert s.execute(select(func.count(Bill.id))).scalar() == 1
        from bizclinik_erp.models import ApprovalRequest, ApprovalStatus
        req = s.get(ApprovalRequest, rid)
        assert req.status == ApprovalStatus.APPROVED
        assert req.result_ref == s.execute(select(Bill)).scalar_one().number


def test_cannot_approve_own_request(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    with get_session() as s:
        sup_id, exp = _supplier_and_expense(s)
        res = approvals.gate(s, doc_type="BILL", amount=645_000.0, title="b",
                             payload=_bill_payload(sup_id, exp, qty=1000),
                             user_id=7, role="AP")
        rid = res["request_id"]
    with get_session() as s:
        with pytest.raises(ValueError, match="your own"):
            approvals.approve(s, rid, approver_user_id=7, approver_role="ADMIN")


def test_approver_below_amount_blocked(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    with get_session() as s:
        sup_id, exp = _supplier_and_expense(s)
        # 2000 * 600 * 1.075 = 1,290,000 — above Accountant's 1m limit
        res = approvals.gate(s, doc_type="BILL", amount=1_290_000.0, title="huge",
                             payload=_bill_payload(sup_id, exp, qty=2000),
                             user_id=3, role="AP")
        rid = res["request_id"]
    with get_session() as s:
        with pytest.raises(ValueError, match="limit is below"):
            approvals.approve(s, rid, approver_user_id=4, approver_role="ACCOUNTANT")
    with get_session() as s:
        # Admin (unlimited) can
        out = approvals.approve(s, rid, approver_user_id=4, approver_role="ADMIN")
        assert out["ref"]


def test_reject_does_not_execute(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    from bizclinik_erp.models import Bill, ApprovalStatus
    from sqlalchemy import select, func
    with get_session() as s:
        sup_id, exp = _supplier_and_expense(s)
        res = approvals.gate(s, doc_type="BILL", amount=645_000.0, title="b",
                             payload=_bill_payload(sup_id, exp, qty=1000),
                             user_id=2, role="AP")
        rid = res["request_id"]
    with get_session() as s:
        approvals.reject(s, rid, approver_user_id=9, approver_role="ADMIN",
                         note="not budgeted")
    with get_session() as s:
        assert s.execute(select(func.count(Bill.id))).scalar() == 0
        from bizclinik_erp.models import ApprovalRequest
        assert s.get(ApprovalRequest, rid).status == ApprovalStatus.REJECTED


def test_set_limit_overrides_default(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    with get_session() as s:
        approvals.set_limit(s, "AP", 500_000)
        assert approvals.role_limit(s, "AP") == 500_000
        assert approvals.requires_approval(s, "AP", 400_000) is False
        assert approvals.requires_approval(s, "AP", 600_000) is True


def test_payroll_gate_executes_on_approval(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import approvals
    from bizclinik_erp.models import Employee, BankAccount, PayrollRun
    from sqlalchemy import select, func
    with get_session() as s:
        emp = Employee(code="E1", name="Worker", monthly_gross=2_000_000,
                       paye_rate=0.1)
        s.add(emp); s.flush()
        bank = s.execute(select(BankAccount)).scalars().first()
        payload = {"period_start": "2026-06-01", "period_end": "2026-06-30",
                   "pay_date": "2026-06-30", "bank_account_id": bank.id,
                   "notes": None,
                   "inputs": [{"employee_id": emp.id, "gross": None,
                               "other_deductions": 0.0}]}
        res = approvals.gate(s, doc_type="PAYROLL", amount=2_000_000.0,
                             title="June payroll", payload=payload,
                             user_id=2, role="ACCOUNTANT")  # over 1m
        assert res["status"] == "pending"
        rid = res["request_id"]
        assert s.execute(select(func.count(PayrollRun.id))).scalar() == 0
    with get_session() as s:
        approvals.approve(s, rid, approver_user_id=9, approver_role="ADMIN")
    with get_session() as s:
        assert s.execute(select(func.count(PayrollRun.id))).scalar() == 1
