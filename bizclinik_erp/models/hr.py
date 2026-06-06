"""HR models — recruitment (job openings → candidates → applications) and
leave management. Sits alongside the existing Employee + Payroll models.

Recruitment mirrors the CRM shape: a JobOpening is worked by moving
JobApplications through stages; hiring a candidate creates a real Employee so
Payroll takes over. LeaveRequest tracks time off against an employee's annual
entitlement.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


# --------------------------------------------------------------------------- #
# Recruitment                                                                 #
# --------------------------------------------------------------------------- #

class OpeningStatus(str, enum.Enum):
    OPEN = "OPEN"
    ON_HOLD = "ON_HOLD"
    FILLED = "FILLED"
    CLOSED = "CLOSED"


class ApplicationStage(str, enum.Enum):
    APPLIED = "APPLIED"
    SCREENING = "SCREENING"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    HIRED = "HIRED"
    REJECTED = "REJECTED"


OPEN_APP_STAGES = (ApplicationStage.APPLIED, ApplicationStage.SCREENING,
                   ApplicationStage.INTERVIEW, ApplicationStage.OFFER)
CLOSED_APP_STAGES = (ApplicationStage.HIRED, ApplicationStage.REJECTED)


class JobOpening(Base):
    __tablename__ = "hr_job_opening"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(120))
    location: Mapped[Optional[str]] = mapped_column(String(120))
    employment_type: Mapped[Optional[str]] = mapped_column(String(40))
    headcount: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[OpeningStatus] = mapped_column(
        Enum(OpeningStatus), default=OpeningStatus.OPEN)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "hr_candidate"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    source: Mapped[Optional[str]] = mapped_column(String(64))   # referral, board, agency…
    resume_url: Mapped[Optional[str]] = mapped_column(String(512))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobApplication(Base):
    __tablename__ = "hr_application"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opening_id: Mapped[int] = mapped_column(ForeignKey("hr_job_opening.id"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("hr_candidate.id"), nullable=False)
    stage: Mapped[ApplicationStage] = mapped_column(
        Enum(ApplicationStage), default=ApplicationStage.APPLIED)
    applied_date: Mapped[date] = mapped_column(Date, default=date.today)
    # Set when the candidate is hired into a real Employee.
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employee.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    opening: Mapped["JobOpening"] = relationship()
    candidate: Mapped["Candidate"] = relationship()


# --------------------------------------------------------------------------- #
# Leave management                                                            #
# --------------------------------------------------------------------------- #

class LeaveType(str, enum.Enum):
    ANNUAL = "ANNUAL"
    SICK = "SICK"
    UNPAID = "UNPAID"
    MATERNITY = "MATERNITY"
    PATERNITY = "PATERNITY"
    OTHER = "OTHER"


class LeaveStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class LeaveRequest(Base):
    __tablename__ = "hr_leave_request"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), nullable=False)
    leave_type: Mapped[LeaveType] = mapped_column(
        Enum(LeaveType), default=LeaveType.ANNUAL)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus), default=LeaveStatus.PENDING)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    approver_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["object"] = relationship("Employee")
