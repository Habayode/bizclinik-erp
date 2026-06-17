"""School module — Phase 1: students and enrolment.

A student's billing identity is an existing Customer (so fee invoices flow
through the normal sales/AR engine), and the Student record is the operational
overlay on top of that Customer. StudentEnrolment is an append-only history of
which class a student sat in for each academic session — withdrawals and
promotions stamp/append rows rather than mutate the past.

New tables only — no changes to existing models — so they provision per-tenant
via Base.metadata.create_all() + ensure_schema().
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (Boolean, Date, DateTime, Enum, ForeignKey, Integer,
                        String, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class StudentStatus(str, enum.Enum):
    """Lifecycle of a student on the roll."""
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"
    GRADUATED = "GRADUATED"
    SUSPENDED = "SUSPENDED"


class Student(Base):
    """A student on the roll. Billing identity is the linked Customer; the
    current class is a denormalised pointer kept in step with the latest open
    StudentEnrolment row."""
    __tablename__ = "student"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admission_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dob: Mapped[Optional[date]] = mapped_column(Date)
    gender: Mapped[Optional[str]] = mapped_column(String(16))
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id"), unique=True, nullable=False)
    current_class_id: Mapped[Optional[int]] = mapped_column(ForeignKey("school_class.id"))
    status: Mapped[StudentStatus] = mapped_column(
        Enum(StudentStatus), default=StudentStatus.ACTIVE)
    status_date: Mapped[Optional[date]] = mapped_column(Date)
    guardian_name: Mapped[Optional[str]] = mapped_column(String(120))
    guardian_phone: Mapped[Optional[str]] = mapped_column(String(64))
    guardian_email: Mapped[Optional[str]] = mapped_column(String(255))
    date_admitted: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(String(512))

    customer = relationship("Customer")
    current_class = relationship("SchoolClass")


class StudentEnrolment(Base):
    """Append-only history: a student's class for one academic session."""
    __tablename__ = "student_enrolment"
    __table_args__ = (UniqueConstraint("student_id", "academic_session_id",
                                       name="uq_enrol_student_session"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"), nullable=False)
    academic_session_id: Mapped[int] = mapped_column(
        ForeignKey("academic_session.id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("school_class.id"), nullable=False)
    enrolment_status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    student = relationship("Student")
    academic_session = relationship("AcademicSession")
    school_class = relationship("SchoolClass")
