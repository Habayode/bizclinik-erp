"""School module — Phase 4: attendance and academic results (GL-free).

Operational records only — neither attendance nor results post to the GL. An
Attendance row stamps a student's daily presence for a class; a StudentResult
captures a per-subject, per-term score (CA + exam -> total -> grade). Both lean
on the existing Student/SchoolClass/AcademicSession/Employee tables and add no
financial behaviour whatsoever.

New tables only — no changes to existing models — so they provision per-tenant
via Base.metadata.create_all() + ensure_schema().
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (Date, DateTime, Enum, Float, ForeignKey, Integer,
                        String)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class AttendanceStatus(str, enum.Enum):
    """How a student was marked for a given day."""
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    EXCUSED = "EXCUSED"


class Attendance(Base):
    """One student's attendance mark for one class on one day."""
    __tablename__ = "school_attendance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("school_class.id"), nullable=False)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus), nullable=False)
    marked_by_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employee.id"))
    remarks: Mapped[Optional[str]] = mapped_column(String(255))

    student = relationship("Student")
    school_class = relationship("SchoolClass")
    marked_by = relationship("Employee")


class StudentResult(Base):
    """A student's score for one subject in one term (CA + exam -> total/grade)."""
    __tablename__ = "school_result"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"), nullable=False)
    class_id: Mapped[Optional[int]] = mapped_column(ForeignKey("school_class.id"))
    academic_session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_session.id"))
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    term_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ca_score: Mapped[float] = mapped_column(Float, default=0.0)
    exam_score: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    grade: Mapped[Optional[str]] = mapped_column(String(4))
    teacher_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employee.id"))
    remarks: Mapped[Optional[str]] = mapped_column(String(255))
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student = relationship("Student")
    school_class = relationship("SchoolClass")
    academic_session = relationship("AcademicSession")
    teacher = relationship("Employee")
