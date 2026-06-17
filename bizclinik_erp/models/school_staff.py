"""School module — Phase 5: teaching staff profiles.

A TeacherProfile is the school-specific overlay on an existing Employee record:
it adds qualification, registration, subjects and class assignments without
duplicating payroll/HR identity (which stays on Employee). One profile per
employee (UNIQUE employee_id). Nothing here touches the GL — payroll for staff
flows through the existing payroll engine, not this module.

New tables only — no changes to existing models — so they provision per-tenant
via Base.metadata.create_all() + ensure_schema().
"""
from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class StaffType(str, enum.Enum):
    """Whether a staff member teaches or is a non-teaching/support role."""
    TEACHING = "TEACHING"
    NON_TEACHING = "NON_TEACHING"


class TeacherProfile(Base):
    """School overlay on an Employee: teaching-staff metadata. One per
    employee (UNIQUE employee_id) — upserts keep it deduplicated."""
    __tablename__ = "teacher_profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employee.id"), unique=True, nullable=False)
    staff_type: Mapped[StaffType] = mapped_column(
        Enum(StaffType), default=StaffType.TEACHING)
    qualification: Mapped[Optional[str]] = mapped_column(String(255))
    registration_number: Mapped[Optional[str]] = mapped_column(String(64))
    subjects_taught: Mapped[Optional[str]] = mapped_column(String(512))
    classes_assigned: Mapped[Optional[str]] = mapped_column(String(255))

    employee = relationship("Employee")
