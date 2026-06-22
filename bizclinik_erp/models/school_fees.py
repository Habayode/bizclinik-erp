"""School module — Phase 2: fee billing (first GL impact).

Billing a student does NOT post to the GL directly: it builds the fee lines from
the Phase 0 fee grid (StudentFeeSchedule) and issues a real SalesInvoice through
the existing sales engine, so revenue routes to each fee's education income
account automatically. StudentFeeBilling is the thin link between a (student,
session, term) and the SalesInvoice that was raised for it — the UniqueConstraint
makes re-running a bill idempotent (no double invoicing).

New tables only — no changes to existing models — so they provision per-tenant
via Base.metadata.create_all() + ensure_schema().
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, Money


class StudentFeeBilling(Base):
    """One fee-billing run for a student in a (session, term): the link to the
    SalesInvoice raised through the normal sales cycle. term_number 0 = annual,
    1-3 = per-term. UniqueConstraint(student, session, term) makes billing
    idempotent — a repeat returns the existing row instead of double-invoicing."""
    __tablename__ = "student_fee_billing"
    __table_args__ = (UniqueConstraint("student_id", "academic_session_id",
                                       "term_number",
                                       name="uq_fee_billing_student_session_term"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"), nullable=False)
    academic_session_id: Mapped[int] = mapped_column(
        ForeignKey("academic_session.id"), nullable=False)
    term_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=annual,1-3
    billing_date: Mapped[Optional[date]] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    sales_invoice_id: Mapped[int] = mapped_column(
        ForeignKey("sales_invoice.id"), nullable=False)
    total_amount: Mapped[float] = mapped_column(Money, default=0.0)

    student = relationship("Student")
    academic_session = relationship("AcademicSession")
    sales_invoice = relationship("SalesInvoice")
