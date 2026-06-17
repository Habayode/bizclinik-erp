"""Parent notifications — log of fee reminders / statements sent to guardians.

Operational only (no GL impact). Records every notification attempt with its
channel, recipient, status and provider reference so the school has an audit
trail of what was sent (or logged, when no SMS gateway is configured).
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class NotifyChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotifyKind(str, enum.Enum):
    FEE_REMINDER = "FEE_REMINDER"
    STATEMENT = "STATEMENT"
    CUSTOM = "CUSTOM"


class NotifyStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"        # transmitted by a real gateway / SMTP
    LOGGED = "LOGGED"    # recorded only (no SMS gateway configured)
    FAILED = "FAILED"


class ParentNotification(Base):
    __tablename__ = "parent_notification"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"), nullable=False)
    channel: Mapped[NotifyChannel] = mapped_column(Enum(NotifyChannel), nullable=False)
    kind: Mapped[NotifyKind] = mapped_column(Enum(NotifyKind), nullable=False)
    recipient: Mapped[Optional[str]] = mapped_column(String(255))   # phone or email
    subject: Mapped[Optional[str]] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[NotifyStatus] = mapped_column(Enum(NotifyStatus), nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(32))
    provider_ref: Mapped[Optional[str]] = mapped_column(String(128))
    error: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    student = relationship("Student")
