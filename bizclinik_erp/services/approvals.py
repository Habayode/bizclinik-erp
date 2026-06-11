"""Approval workflow service — per-role limits + a deferred-execution gate.

Usage from a page/service:

    res = approvals.gate(
        session, doc_type="BILL", amount=ngn_total, title="Bill — ACME",
        payload={...},                       # kwargs to re-run on approval
        user_id=uid, role=current_role,
    )
    # res["status"] == "done"     -> executed immediately (under limit); res["ref"]
    # res["status"] == "pending"  -> queued for approval; res["request_id"]

On approval, ``approve()`` re-runs the registered executor for ``doc_type`` with
the stored payload, so the real document is created + posted exactly as if it
had gone through directly. Rejected requests never run, so they consume no
document number.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApprovalLimit, ApprovalRequest, ApprovalStatus

# Default per-role NGN authorisation ceilings (None = unlimited). Editable per
# tenant on the Approvals page; these apply when no row is set.
DEFAULT_LIMITS: dict[str, Optional[float]] = {
    "ADMIN": None,
    "ACCOUNTANT": 1_000_000.0,
    "AP": 250_000.0,
    "SALES": 0.0,
    "VIEWER": 0.0,
}

# Doc types that route through approval.
DOC_TYPES = ("BILL", "PO", "PAYMENT", "PAYROLL")
DOC_LABELS = {"BILL": "Bill", "PO": "Purchase order",
              "PAYMENT": "Payment", "PAYROLL": "Payroll run"}

_EPS = 0.005


def _now() -> datetime:
    return datetime.utcnow()


def _role_str(role) -> str:
    if role is None:
        return ""
    return getattr(role, "value", str(role)).upper()


# --------------------------------------------------------------------------- #
# Limits                                                                      #
# --------------------------------------------------------------------------- #

def role_limit(session: Session, role) -> Optional[float]:
    """Effective NGN limit for a role (None = unlimited). Falls back to the
    DEFAULT_LIMITS constant when no row is configured for the tenant."""
    rs = _role_str(role)
    row = session.execute(
        select(ApprovalLimit).where(ApprovalLimit.role == rs)).scalar_one_or_none()
    if row is not None:
        return row.limit_ngn  # may be None (unlimited)
    # Known roles use their default; an unknown/empty role (e.g. dev no-auth
    # mode) is treated as unlimited so single-user installs aren't gated.
    return DEFAULT_LIMITS.get(rs)


def set_limit(session: Session, role, limit_ngn: Optional[float]) -> ApprovalLimit:
    rs = _role_str(role)
    row = session.execute(
        select(ApprovalLimit).where(ApprovalLimit.role == rs)).scalar_one_or_none()
    if row is None:
        row = ApprovalLimit(role=rs)
        session.add(row)
    row.limit_ngn = limit_ngn
    row.updated_at = _now()
    session.flush()
    return row


def list_limits(session: Session) -> list[dict]:
    out = []
    for rs in DEFAULT_LIMITS:
        lim = role_limit(session, rs)
        out.append({"role": rs, "limit_ngn": lim,
                    "unlimited": lim is None})
    return out


def seed_limits(session: Session) -> None:
    """Materialise the default limit rows if absent (idempotent)."""
    for rs, lim in DEFAULT_LIMITS.items():
        exists = session.execute(
            select(ApprovalLimit).where(ApprovalLimit.role == rs)).scalar_one_or_none()
        if exists is None:
            session.add(ApprovalLimit(role=rs, limit_ngn=lim))
    session.flush()


def requires_approval(session: Session, role, amount: float) -> bool:
    lim = role_limit(session, role)
    return lim is not None and amount > lim + _EPS


def can_approve(session: Session, role, amount: float) -> bool:
    lim = role_limit(session, role)
    return lim is None or amount <= lim + _EPS


# --------------------------------------------------------------------------- #
# Deferred executors — re-run the original call on approval                    #
# --------------------------------------------------------------------------- #

def _d(v: Optional[str]) -> Optional[date]:
    return date.fromisoformat(v) if v else None


def _exec_bill(session: Session, p: dict) -> str:
    from .purchase import receive_bill, POLineInput
    lines = [POLineInput(**l) for l in p["lines"]]
    bill = receive_bill(session, supplier_id=p["supplier_id"],
                        bill_date=_d(p["bill_date"]), due_date=_d(p.get("due_date")),
                        lines=lines, notes=p.get("notes"),
                        currency_code=p.get("currency_code", "NGN"),
                        fx_rate=p.get("fx_rate"))
    return bill.number


def _exec_po(session: Session, p: dict) -> str:
    from .purchase import create_purchase_order, POLineInput
    lines = [POLineInput(**l) for l in p["lines"]]
    po = create_purchase_order(session, supplier_id=p["supplier_id"],
                               order_date=_d(p["order_date"]), lines=lines,
                               notes=p.get("notes"))
    return po.number


def _exec_payment(session: Session, p: dict) -> str:
    from .purchase import record_payment
    pay = record_payment(session, supplier_id=p["supplier_id"],
                         payment_date=_d(p["payment_date"]), amount=p["amount"],
                         bank_account_id=p["bank_account_id"],
                         bill_id=p.get("bill_id"), method=p.get("method", "BANK"),
                         reference=p.get("reference"),
                         settlement_fx_rate=p.get("settlement_fx_rate"))
    return pay.number


def _exec_payroll(session: Session, p: dict) -> str:
    from .payroll import run_payroll, PayslipInput
    inputs = [PayslipInput(**i) for i in p["inputs"]]
    run = run_payroll(session, period_start=_d(p["period_start"]),
                      period_end=_d(p["period_end"]), pay_date=_d(p["pay_date"]),
                      inputs=inputs, bank_account_id=p["bank_account_id"],
                      notes=p.get("notes"))
    return run.number


EXECUTORS: dict[str, Callable[[Session, dict], str]] = {
    "BILL": _exec_bill, "PO": _exec_po,
    "PAYMENT": _exec_payment, "PAYROLL": _exec_payroll,
}


def _execute(session: Session, doc_type: str, payload: dict) -> str:
    fn = EXECUTORS.get(doc_type)
    if not fn:
        raise ValueError(f"No executor for doc_type {doc_type!r}.")
    return fn(session, payload)


# --------------------------------------------------------------------------- #
# Gate / submit / decide                                                      #
# --------------------------------------------------------------------------- #

def gate(session: Session, *, doc_type: str, amount: float, title: str,
         payload: dict, user_id: Optional[int], role) -> dict:
    """Execute now if within the submitter's limit, else queue for approval."""
    if doc_type not in EXECUTORS:
        raise ValueError(f"Unknown doc_type {doc_type!r}.")
    if requires_approval(session, role, amount):
        req = submit(session, doc_type=doc_type, amount=amount, title=title,
                     payload=payload, user_id=user_id, role=role)
        return {"status": "pending", "request_id": req.id,
                "limit": role_limit(session, role)}
    ref = _execute(session, doc_type, payload)
    return {"status": "done", "ref": ref}


def submit(session: Session, *, doc_type: str, amount: float, title: str,
           payload: dict, user_id: Optional[int], role) -> ApprovalRequest:
    req = ApprovalRequest(
        doc_type=doc_type, title=title, amount_ngn=round(amount, 2),
        payload_json=json.dumps(payload), status=ApprovalStatus.PENDING,
        requested_by_user_id=user_id, requested_role=_role_str(role))
    session.add(req)
    session.flush()
    return req


def list_requests(session: Session, *, status: Optional[ApprovalStatus] = None,
                  requested_by: Optional[int] = None) -> list[ApprovalRequest]:
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if status is not None:
        stmt = stmt.where(ApprovalRequest.status == status)
    if requested_by is not None:
        stmt = stmt.where(ApprovalRequest.requested_by_user_id == requested_by)
    return list(session.execute(stmt).scalars())


def list_pending(session: Session) -> list[ApprovalRequest]:
    return list_requests(session, status=ApprovalStatus.PENDING)


def pending_count(session: Session) -> int:
    return len(list_pending(session))


def approve(session: Session, request_id: int, *, approver_user_id: Optional[int],
            approver_role) -> dict:
    """Approve + execute a pending request. The approver's role limit must cover
    the amount, and they may not approve their own request."""
    req = session.get(ApprovalRequest, request_id)
    if not req:
        raise ValueError(f"Request {request_id} not found.")
    if req.status != ApprovalStatus.PENDING:
        raise ValueError(f"Request {request_id} is already {req.status.value}.")
    if approver_user_id is not None and approver_user_id == req.requested_by_user_id:
        raise ValueError("You cannot approve your own request.")
    if not can_approve(session, approver_role, req.amount_ngn):
        raise ValueError("Your approval limit is below this amount.")
    ref = _execute(session, req.doc_type, json.loads(req.payload_json))
    req.status = ApprovalStatus.APPROVED
    req.approver_user_id = approver_user_id
    req.decided_at = _now()
    req.result_ref = ref
    session.flush()
    return {"request_id": req.id, "ref": ref, "doc_type": req.doc_type}


def reject(session: Session, request_id: int, *, approver_user_id: Optional[int],
           approver_role, note: Optional[str] = None) -> ApprovalRequest:
    req = session.get(ApprovalRequest, request_id)
    if not req:
        raise ValueError(f"Request {request_id} not found.")
    if req.status != ApprovalStatus.PENDING:
        raise ValueError(f"Request {request_id} is already {req.status.value}.")
    if not can_approve(session, approver_role, req.amount_ngn):
        raise ValueError("Your approval limit is below this amount.")
    req.status = ApprovalStatus.REJECTED
    req.approver_user_id = approver_user_id
    req.decided_at = _now()
    req.note = note
    session.flush()
    return req


def cancel(session: Session, request_id: int, *, user_id: Optional[int]) -> ApprovalRequest:
    """The requester withdraws their own pending request."""
    req = session.get(ApprovalRequest, request_id)
    if not req:
        raise ValueError(f"Request {request_id} not found.")
    if req.status != ApprovalStatus.PENDING:
        raise ValueError(f"Request {request_id} is already {req.status.value}.")
    req.status = ApprovalStatus.CANCELLED
    req.decided_at = _now()
    session.flush()
    return req
