"""School service — Phase 2: fee billing (first GL impact).

Billing a student gathers the applicable fee-grid cells (StudentFeeSchedule) for
the student's class + the requested term, builds invoice lines from the fee
types' income-account-wired products, and raises a real SalesInvoice through the
existing ``sales.issue_invoice`` — so the revenue posts to each fee's education
income account with NO parallel ledger and NO direct ``ledger.post_journal``
call from school code. Fees are VAT-exempt, so every line uses tax_rate=0.0.

Billing is idempotent: a StudentFeeBilling row unique on (student, session, term)
short-circuits a repeat so a class run never double-invoices. Mutating calls
require the ``manage.school`` permission.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (AcademicSession, DocStatus, SalesInvoice, Student,
                      StudentFeeBilling, StudentFeeSchedule, StudentStatus)
from . import sales


def bill_student(session: Session, *, student_id: int, academic_session_id: int,
                 term_number: int, invoice_date: date,
                 include_annual: bool = False,
                 due_date: Optional[date] = None) -> Optional[StudentFeeBilling]:
    """Bill one student for a (session, term). Idempotent on (student, session,
    term). Gathers fee-grid rows for the student's class (or school-wide rows
    where class_id IS NULL) for the requested term — plus the annual/one-off
    (term 0) rows when ``include_annual`` — and raises ONE SalesInvoice through
    ``sales.issue_invoice``. Returns the StudentFeeBilling row, or None when
    there is nothing to bill."""
    authz.require_perm("manage.school")
    if term_number not in (0, 1, 2, 3):
        raise ValueError("term_number must be 0 (annual/one-off) or 1-3.")
    student = session.get(Student, student_id)
    if student is None:
        raise ValueError("Student not found.")
    if session.get(AcademicSession, academic_session_id) is None:
        raise ValueError("Academic session not found.")

    # Idempotency: a bill for this (student, session, term) already exists.
    existing = session.execute(select(StudentFeeBilling).where(
        StudentFeeBilling.student_id == student_id,
        StudentFeeBilling.academic_session_id == academic_session_id,
        StudentFeeBilling.term_number == term_number)).scalar_one_or_none()
    if existing is not None:
        return existing

    terms = [term_number]
    if include_annual and term_number != 0:
        terms.append(0)

    rows = session.execute(select(StudentFeeSchedule).where(
        StudentFeeSchedule.academic_session_id == academic_session_id,
        StudentFeeSchedule.term_number.in_(terms),
        StudentFeeSchedule.is_active == True,  # noqa: E712
        or_(StudentFeeSchedule.class_id == student.current_class_id,
            StudentFeeSchedule.class_id.is_(None)))).scalars().all()

    lines = [sales.LineInput(product_id=r.fee_type.product_id,
                             description=r.fee_type.name, qty=1,
                             unit_price=r.amount, tax_rate=0.0)
             for r in rows if r.amount]
    if not lines:
        return None

    inv = sales.issue_invoice(session, customer_id=student.customer_id,
                              invoice_date=invoice_date, due_date=due_date,
                              lines=lines)
    billing = StudentFeeBilling(student_id=student_id,
                                academic_session_id=academic_session_id,
                                term_number=term_number,
                                billing_date=invoice_date, due_date=due_date,
                                sales_invoice_id=inv.id,
                                total_amount=inv.grand_total)
    session.add(billing)
    session.flush()
    return billing


def generate_class_fees(session: Session, *, class_id: int,
                        academic_session_id: int, term_number: int,
                        invoice_date: date, include_annual: bool = False,
                        due_date: Optional[date] = None) -> dict:
    """Bill every active student in a class for a (session, term). Already-billed
    students are skipped (idempotent). Returns a {billed, skipped, errors}
    summary."""
    authz.require_perm("manage.school")
    students = session.execute(select(Student).where(
        Student.current_class_id == class_id,
        Student.status == StudentStatus.ACTIVE).order_by(
            Student.admission_no)).scalars().all()
    result = {"billed": 0, "skipped": 0, "errors": []}
    for st_ in students:
        already = session.execute(select(StudentFeeBilling).where(
            StudentFeeBilling.student_id == st_.id,
            StudentFeeBilling.academic_session_id == academic_session_id,
            StudentFeeBilling.term_number == term_number)).scalar_one_or_none()
        if already is not None:
            result["skipped"] += 1
            continue
        try:
            billing = bill_student(session, student_id=st_.id,
                                   academic_session_id=academic_session_id,
                                   term_number=term_number,
                                   invoice_date=invoice_date,
                                   include_annual=include_annual,
                                   due_date=due_date)
            if billing is None:
                result["skipped"] += 1
            else:
                result["billed"] += 1
        except Exception as e:  # noqa: BLE001 — collect per-student failures
            result["errors"].append(f"{st_.admission_no}: {e}")
    return result


# === Phase 3: collections, statements, defaulters =========================

def record_fee_payment(session: Session, *, student_id: int,
                       sales_invoice_id: int, amount: float, payment_date: date,
                       bank_account_id: int, method: str = "BANK",
                       reference: Optional[str] = None):
    """Record a fee payment against a student's SalesInvoice. Routes through the
    existing ``sales.record_receipt`` (DR Bank / CR AR) — no direct GL post from
    school code. Returns the Receipt."""
    authz.require_perm("manage.school")
    student = session.get(Student, student_id)
    if student is None:
        raise ValueError("Student not found.")
    return sales.record_receipt(
        session, customer_id=student.customer_id, receipt_date=payment_date,
        amount=amount, bank_account_id=bank_account_id,
        invoice_id=sales_invoice_id, method=method, reference=reference)


def _student_invoices(session: Session, student_id: int):
    """The SalesInvoices raised for one student (via the student's customer)."""
    student = session.get(Student, student_id)
    if student is None:
        raise ValueError("Student not found.")
    return session.execute(select(SalesInvoice).where(
        SalesInvoice.customer_id == student.customer_id)).scalars().all()


def student_balance(session: Session, student_id: int) -> dict:
    """Roll up a student's fee position across all their SalesInvoices:
    {billed, paid, outstanding}."""
    invs = _student_invoices(session, student_id)
    billed = round(sum(i.grand_total for i in invs), 2)
    paid = round(sum(i.amount_paid for i in invs), 2)
    return {"billed": billed, "paid": paid,
            "outstanding": round(billed - paid, 2)}


def class_fee_status(session: Session, class_id: int,
                     academic_session_id: int) -> list:
    """Per-student fee position for the students billed in a class for an
    academic session. A student appears when they have at least one
    StudentFeeBilling row for that (class, session). Returns a list of
    {admission_no, name, billed, paid, outstanding} ordered by admission_no."""
    rows = session.execute(
        select(Student).join(
            StudentFeeBilling, StudentFeeBilling.student_id == Student.id).where(
            Student.current_class_id == class_id,
            StudentFeeBilling.academic_session_id == academic_session_id)
        .distinct().order_by(Student.admission_no)).scalars().all()
    out = []
    for st_ in rows:
        bal = student_balance(session, st_.id)
        out.append({"admission_no": st_.admission_no,
                    "name": f"{st_.first_name} {st_.last_name}",
                    "billed": bal["billed"], "paid": bal["paid"],
                    "outstanding": bal["outstanding"]})
    return out


def defaulters(session: Session, academic_session_id: int,
               min_outstanding: float = 0.01) -> list:
    """Students with an outstanding fee balance for an academic session, sorted
    by outstanding descending. A student is in scope when they have a
    StudentFeeBilling row for the session. Returns a list of
    {admission_no, name, billed, paid, outstanding}."""
    students = session.execute(
        select(Student).join(
            StudentFeeBilling, StudentFeeBilling.student_id == Student.id).where(
            StudentFeeBilling.academic_session_id == academic_session_id)
        .distinct()).scalars().all()
    out = []
    for st_ in students:
        bal = student_balance(session, st_.id)
        if bal["outstanding"] >= min_outstanding:
            out.append({"admission_no": st_.admission_no,
                        "name": f"{st_.first_name} {st_.last_name}",
                        "billed": bal["billed"], "paid": bal["paid"],
                        "outstanding": bal["outstanding"]})
    out.sort(key=lambda r: r["outstanding"], reverse=True)
    return out
