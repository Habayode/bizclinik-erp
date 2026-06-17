"""School service — Phase 0: academic calendar, classes, and the fee grid.

Pure master-data setup; nothing here posts to the GL. A FeeType is created as a
non-stockable Product wired to an education income account, so when fees are
billed (Phase 2) the existing ``sales.issue_invoice`` routes the revenue to the
right account automatically. Mutating calls require the ``manage.school``
permission (enforced here so both the UI and any future API are covered).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (Account, AcademicSession, FeeType, Product, SchoolClass,
                      StudentFeeSchedule, Term)


# --------------------------------------------------------------------------- #
# Academic calendar                                                           #
# --------------------------------------------------------------------------- #

def create_academic_session(session: Session, *, session_code: str,
                            name: Optional[str] = None,
                            start_date: Optional[date] = None,
                            end_date: Optional[date] = None,
                            make_current: bool = False) -> AcademicSession:
    authz.require_perm("manage.school")
    code = (session_code or "").strip()
    if not code:
        raise ValueError("session_code is required (e.g. '2025/2026').")
    if session.execute(select(AcademicSession).where(
            AcademicSession.session_code == code)).scalar_one_or_none():
        raise ValueError(f"Academic session {code!r} already exists.")
    if make_current:
        for s in session.execute(select(AcademicSession)).scalars():
            s.is_current = False
    obj = AcademicSession(session_code=code, name=(name or code),
                          start_date=start_date, end_date=end_date,
                          is_current=make_current)
    session.add(obj); session.flush()
    return obj


def create_term(session: Session, *, academic_session_id: int, term_number: int,
                name: Optional[str] = None, start_date: Optional[date] = None,
                end_date: Optional[date] = None) -> Term:
    authz.require_perm("manage.school")
    if term_number not in (1, 2, 3):
        raise ValueError("term_number must be 1, 2 or 3.")
    if session.get(AcademicSession, academic_session_id) is None:
        raise ValueError("Academic session not found.")
    if session.execute(select(Term).where(
            Term.academic_session_id == academic_session_id,
            Term.term_number == term_number)).scalar_one_or_none():
        raise ValueError(f"Term {term_number} already exists for that session.")
    obj = Term(academic_session_id=academic_session_id, term_number=term_number,
               name=(name or f"Term {term_number}"),
               start_date=start_date, end_date=end_date)
    session.add(obj); session.flush()
    return obj


# --------------------------------------------------------------------------- #
# Classes                                                                     #
# --------------------------------------------------------------------------- #

def create_school_class(session: Session, *, class_code: str, name: str,
                        form_level: Optional[int] = None,
                        arm: Optional[str] = None,
                        form_tutor_employee_id: Optional[int] = None,
                        capacity: Optional[int] = None) -> SchoolClass:
    authz.require_perm("manage.school")
    code = (class_code or "").strip()
    if not code:
        raise ValueError("class_code is required (e.g. 'JSS1A').")
    if not (name or "").strip():
        raise ValueError("Class name is required.")
    if session.execute(select(SchoolClass).where(
            SchoolClass.class_code == code)).scalar_one_or_none():
        raise ValueError(f"Class {code!r} already exists.")
    obj = SchoolClass(class_code=code, name=name.strip(), form_level=form_level,
                      arm=(arm or None),
                      form_tutor_employee_id=form_tutor_employee_id,
                      capacity=capacity)
    session.add(obj); session.flush()
    return obj


# --------------------------------------------------------------------------- #
# Fee types (backed by income-account-wired products)                         #
# --------------------------------------------------------------------------- #

def create_fee_type(session: Session, *, code: str, name: str,
                    income_account_code: str, is_mandatory: bool = True,
                    sort_order: int = 0) -> FeeType:
    """Create a fee type backed by a non-stockable Product wired to the given
    education income account (e.g. 4400 Tuition). Fees are VAT-exempt, so the
    product carries no tax — issue_invoice posts no Output VAT line."""
    authz.require_perm("manage.school")
    code = (code or "").strip().upper()
    if not code:
        raise ValueError("Fee code is required (e.g. 'TUI').")
    if not (name or "").strip():
        raise ValueError("Fee name is required.")
    if session.execute(select(FeeType).where(FeeType.code == code)).scalar_one_or_none():
        raise ValueError(f"Fee type {code!r} already exists.")
    acct = session.execute(select(Account).where(
        Account.code == str(income_account_code))).scalar_one_or_none()
    if acct is None or not acct.is_postable:
        raise ValueError(
            f"Income account {income_account_code!r} not found or not postable.")
    sku = f"FEE-{code}"
    prod = session.execute(select(Product).where(Product.sku == sku)).scalar_one_or_none()
    if prod is None:
        prod = Product(sku=sku, name=name.strip(), unit="term", is_stockable=False,
                       income_account_id=acct.id, standard_price=0.0)
        session.add(prod); session.flush()
    else:
        prod.income_account_id = acct.id
        prod.is_stockable = False
    obj = FeeType(code=code, name=name.strip(), product_id=prod.id,
                  is_mandatory=is_mandatory, sort_order=sort_order)
    session.add(obj); session.flush()
    return obj


# --------------------------------------------------------------------------- #
# Fee grid                                                                     #
# --------------------------------------------------------------------------- #

def set_fee_schedule(session: Session, *, academic_session_id: int,
                     fee_type_id: int, amount: float,
                     class_id: Optional[int] = None,
                     term_number: int = 0) -> StudentFeeSchedule:
    """Idempotent upsert of one fee-grid cell. term_number 1-3 = per-term;
    0 = annual/one-off. class_id None = a school-wide fee."""
    authz.require_perm("manage.school")
    if term_number not in (0, 1, 2, 3):
        raise ValueError("term_number must be 0 (annual/one-off) or 1-3.")
    if amount < 0:
        raise ValueError("amount must be >= 0.")
    if session.get(AcademicSession, academic_session_id) is None:
        raise ValueError("Academic session not found.")
    if session.get(FeeType, fee_type_id) is None:
        raise ValueError("Fee type not found.")
    q = select(StudentFeeSchedule).where(
        StudentFeeSchedule.academic_session_id == academic_session_id,
        StudentFeeSchedule.fee_type_id == fee_type_id,
        StudentFeeSchedule.term_number == term_number)
    q = (q.where(StudentFeeSchedule.class_id == class_id) if class_id is not None
         else q.where(StudentFeeSchedule.class_id.is_(None)))
    row = session.execute(q).scalar_one_or_none()
    if row is None:
        row = StudentFeeSchedule(academic_session_id=academic_session_id,
                                 class_id=class_id, fee_type_id=fee_type_id,
                                 term_number=term_number, amount=amount)
        session.add(row)
    else:
        row.amount = amount
        row.is_active = True
    session.flush()
    return row


def validate_fee_structure(session: Session, academic_session_id: int) -> dict:
    """Read-only summary of the fee grid for a session (cells + total)."""
    rows = session.execute(select(StudentFeeSchedule).where(
        StudentFeeSchedule.academic_session_id == academic_session_id,
        StudentFeeSchedule.is_active == True)).scalars().all()   # noqa: E712
    by_term: dict[int, float] = {}
    for r in rows:
        by_term[r.term_number] = round(by_term.get(r.term_number, 0.0) + r.amount, 2)
    return {"cells": len(rows),
            "total_amount": round(sum(r.amount for r in rows), 2),
            "by_term": by_term}
