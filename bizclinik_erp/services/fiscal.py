"""Fiscal period close/lock service.

Use `check_open(session, entry_date)` before posting any journal. Closed
periods block all writes unless the caller has the `close.period` permission
(checked at the UI/CLI layer, not here).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.fiscal import FiscalPeriod, PeriodStatus
from .audit import record
from ..models.audit import AuditAction


# ---- exception ------------------------------------------------------------


class PeriodClosedError(RuntimeError):
    """Raised when a journal entry is posted into a closed/locked period."""

    def __init__(self, period: FiscalPeriod):
        self.period = period
        super().__init__(
            f"Fiscal period {period.year}-{period.month:02d} is "
            f"{period.status.value} — refusing to post entry."
        )


# ---- helpers --------------------------------------------------------------


def _bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    _, last = calendar.monthrange(year, month)
    end = date(year, month, last)
    return start, end


def get_or_create_period(session: Session, year: int, month: int) -> FiscalPeriod:
    p = session.execute(
        select(FiscalPeriod).where(
            FiscalPeriod.year == year, FiscalPeriod.month == month
        )
    ).scalar_one_or_none()
    if p:
        return p
    start, end = _bounds(year, month)
    p = FiscalPeriod(year=year, month=month, period_start=start, period_end=end,
                      status=PeriodStatus.OPEN)
    session.add(p)
    session.flush()
    return p


def get_period_for(session: Session, on: date) -> FiscalPeriod:
    return get_or_create_period(session, on.year, on.month)


# ---- enforcement (called by ledger.post_journal) --------------------------


def check_open(session: Session, entry_date: date, *, allow_override: bool = False) -> None:
    """Raise PeriodClosedError if the period is closed/locked.

    `allow_override=True` lets ADMIN with `close.period` permission post into
    a CLOSED period (but never a LOCKED one).
    """
    p = get_period_for(session, entry_date)
    if p.status == PeriodStatus.LOCKED:
        raise PeriodClosedError(p)
    if p.status == PeriodStatus.CLOSED and not allow_override:
        raise PeriodClosedError(p)


# ---- period management ----------------------------------------------------


def close_period(session: Session, year: int, month: int, *,
                  user_id: Optional[int] = None, notes: Optional[str] = None) -> FiscalPeriod:
    p = get_or_create_period(session, year, month)
    if p.status == PeriodStatus.LOCKED:
        raise ValueError(f"Cannot close a LOCKED period ({year}-{month:02d}).")
    p.status = PeriodStatus.CLOSED
    p.closed_at = datetime.utcnow()
    p.closed_by_user_id = user_id
    if notes:
        p.notes = notes
    record(session, action=AuditAction.CLOSE_PERIOD, entity_type="fiscal_period",
           entity_id=p.id,
           description=f"Closed period {year}-{month:02d}",
           user_id=user_id, source="services.fiscal")
    return p


def lock_period(session: Session, year: int, month: int, *,
                 user_id: Optional[int] = None) -> FiscalPeriod:
    p = get_or_create_period(session, year, month)
    p.status = PeriodStatus.LOCKED
    p.locked_at = datetime.utcnow()
    p.locked_by_user_id = user_id
    if not p.closed_at:
        p.closed_at = p.locked_at
        p.closed_by_user_id = user_id
    record(session, action=AuditAction.LOCK_PERIOD, entity_type="fiscal_period",
           entity_id=p.id,
           description=f"Locked period {year}-{month:02d}",
           user_id=user_id, source="services.fiscal")
    return p


def reopen_period(session: Session, year: int, month: int, *,
                   user_id: Optional[int] = None, reason: str) -> FiscalPeriod:
    """Reopen a CLOSED (not LOCKED) period. ADMIN-only; the caller must check
    permissions before invoking. Writes a strong audit-log entry."""
    if not reason or len(reason.strip()) < 5:
        raise ValueError("A non-trivial reason is required to reopen a period.")
    p = get_or_create_period(session, year, month)
    if p.status == PeriodStatus.LOCKED:
        raise ValueError("LOCKED periods cannot be reopened without admin unlock.")
    p.status = PeriodStatus.OPEN
    p.closed_at = None
    p.closed_by_user_id = None
    record(session, action=AuditAction.REOPEN_PERIOD, entity_type="fiscal_period",
           entity_id=p.id,
           description=f"Reopened period {year}-{month:02d}: {reason}",
           payload={"reason": reason},
           user_id=user_id, source="services.fiscal")
    return p


def list_periods(session: Session, year: Optional[int] = None) -> list[FiscalPeriod]:
    q = select(FiscalPeriod).order_by(FiscalPeriod.year.desc(), FiscalPeriod.month.desc())
    if year:
        q = q.where(FiscalPeriod.year == year)
    return list(session.execute(q).scalars())
