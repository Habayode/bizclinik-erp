"""Fiscal periods.

One row per (year, month) pair. Status transitions:
    OPEN     — journals can post freely
    CLOSED   — soft lock; an ADMIN may still override
    LOCKED   — hard lock; no overrides without re-opening
    REOPENED — a previously CLOSED period that was reopened (audit trail)

`services.fiscal.check_open(entry_date)` is called by post_journal() to
enforce these rules. Closing a period writes an audit_log row.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class PeriodStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class FiscalPeriod(Base):
    __tablename__ = "fiscal_period"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_fiscal_period_year_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PeriodStatus] = mapped_column(Enum(PeriodStatus), default=PeriodStatus.OPEN)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    closed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    locked_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    notes: Mapped[Optional[str]] = mapped_column(String(255))

    def __repr__(self) -> str:
        return f"<FiscalPeriod {self.year}-{self.month:02d} {self.status.value}>"
