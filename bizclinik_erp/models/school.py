"""School module — Phase 0 scaffolding (academic calendar, classes, fee grid).

An OPERATIONAL overlay on the accounting core for school clients (e.g. OTASCH).
None of these models post to the GL. Money flows only through the existing
sales cycle: a FeeType is a non-stockable Product wired to an education income
account (4400-4470), a fee invoice IS a SalesInvoice, and a student's billing
identity is a Customer (added in Phase 1). Academic sessions/terms are school
dimensions — explicitly NOT fiscal periods (the GL keeps its own calendar).

New tables only — no changes to existing models — so they provision per-tenant
via Base.metadata.create_all() + ensure_schema().
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import (Boolean, Date, Float, ForeignKey, Integer, String,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class AcademicSession(Base):
    """A school year, e.g. '2025/2026'. Operational dimension, not a fiscal period."""
    __tablename__ = "academic_session"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Term(Base):
    """A term within a session (1st/2nd/3rd)."""
    __tablename__ = "school_term"
    __table_args__ = (UniqueConstraint("academic_session_id", "term_number",
                                       name="uq_term_session_number"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_session_id: Mapped[int] = mapped_column(
        ForeignKey("academic_session.id"), nullable=False)
    term_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..3
    name: Mapped[Optional[str]] = mapped_column(String(64))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    academic_session: Mapped[AcademicSession] = relationship()


class SchoolClass(Base):
    """A class/grade, e.g. 'JSS1A'. The form tutor is an existing Employee."""
    __tablename__ = "school_class"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    form_level: Mapped[Optional[int]] = mapped_column(Integer)
    arm: Mapped[Optional[str]] = mapped_column(String(16))
    form_tutor_employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employee.id"))
    capacity: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    form_tutor = relationship("Employee")


class FeeType(Base):
    """A billable fee (Tuition, Exam, Uniform…) — a thin school label over a
    non-stockable Product whose income_account_id routes revenue to the right
    education COA account when issue_invoice posts."""
    __tablename__ = "fee_type"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), unique=True, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product = relationship("Product")


class StudentFeeSchedule(Base):
    """The fee grid: what a class pays for a fee type in a given term.
    term_number 1-3 = per-term fee; 0 = annual/one-off (billed once per session).
    class_id NULL = a school-wide fee (applies to every class)."""
    __tablename__ = "student_fee_schedule"
    __table_args__ = (UniqueConstraint("academic_session_id", "class_id",
                                       "fee_type_id", "term_number",
                                       name="uq_fee_schedule"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_session_id: Mapped[int] = mapped_column(
        ForeignKey("academic_session.id"), nullable=False)
    class_id: Mapped[Optional[int]] = mapped_column(ForeignKey("school_class.id"))
    fee_type_id: Mapped[int] = mapped_column(ForeignKey("fee_type.id"), nullable=False)
    term_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=annual
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    fee_type = relationship("FeeType")
    school_class = relationship("SchoolClass")
    academic_session = relationship("AcademicSession")
