"""Approval workflow — per-role spending limits + an approval queue.

Money-out documents (bills, purchase orders, payments) and payroll runs that
exceed the submitter's role limit are captured as a PENDING ApprovalRequest
instead of posting. An authorised approver (whose role limit covers the amount)
clears it, and only then is the underlying document created and posted.

The request stores the original call as a JSON payload + doc_type so the
service can execute it verbatim on approval (deferred execution). This keeps the
existing posting logic untouched and means rejected requests never consume a
document number.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ApprovalLimit(Base):
    """Per-role authorisation ceiling (NGN). limit_ngn NULL = unlimited."""
    __tablename__ = "approval_limit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    limit_ngn: Mapped[Optional[float]] = mapped_column(Float)  # None = unlimited
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_request"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)  # BILL/PO/PAYMENT/PAYROLL
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_ngn: Mapped[float] = mapped_column(Float, default=0.0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    requested_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    requested_role: Mapped[Optional[str]] = mapped_column(String(32))
    approver_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    note: Mapped[Optional[str]] = mapped_column(Text)
    result_ref: Mapped[Optional[str]] = mapped_column(String(64))  # e.g. "BIL-0007"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
