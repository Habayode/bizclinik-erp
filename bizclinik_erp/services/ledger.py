"""General Ledger service.

post_journal() is the single chokepoint for every GL impact. It validates
debit == credit, persists the lines, and stamps the entry POSTED. Trial
Balance and account inquiries read from the persisted lines.
"""
from __future__ import annotations
from ..money import msum

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    AccountType,
    DocStatus,
    JournalEntry,
    JournalLine,
)
from ..models.master import NORMAL_BALANCE
from .numbering import next_number


# ---- input shape ------------------------------------------------------------


@dataclass
class JELine:
    """Lightweight DTO for a posting line. Either debit or credit per line."""
    account_id: int
    debit: float = 0.0
    credit: float = 0.0
    memo: Optional[str] = None
    customer_id: Optional[int] = None
    supplier_id: Optional[int] = None


# ---- posting ---------------------------------------------------------------


def post_journal(
    session: Session,
    entry_date: date,
    memo: str,
    lines: Iterable[JELine],
    *,
    source_kind: Optional[str] = None,
    source_id: Optional[int] = None,
    entry_no: Optional[str] = None,
    allow_closed_period: bool = False,
    user_id: Optional[int] = None,
) -> JournalEntry:
    """Create + post a balanced JournalEntry. Raises if DR != CR.

    Refuses to post into a CLOSED or LOCKED fiscal period unless
    `allow_closed_period=True` (ADMIN override only). LOCKED is never
    overridable. See `services.fiscal.check_open`.
    """
    line_list = list(lines)
    if not line_list:
        raise ValueError("Refusing to post an empty journal entry.")

    # A manual journal (no source document) requires post.journal at the service
    # layer — defense-in-depth beyond the page gate. Service-driven postings
    # (sales/purchase/payroll/banking/reversal/etc.) always carry a source_kind
    # and are gated by their own service permission, so they pass through here.
    if source_kind is None:
        from .. import authz
        authz.require_perm("post.journal")

    total_dr = msum(l.debit for l in line_list)
    total_cr = msum(l.credit for l in line_list)
    if abs(total_dr - total_cr) > 0.01:
        raise ValueError(
            f"Journal entry unbalanced: DR {total_dr:,.2f} != CR {total_cr:,.2f}. "
            "Refusing to post."
        )
    if total_dr <= 0:
        raise ValueError("Refusing to post a zero-value journal entry.")

    # Period-close enforcement. Import lazily so legacy code that imports
    # ledger before the fiscal model is registered (e.g. fresh-test setup)
    # still works.
    try:
        from .fiscal import check_open
    except ImportError as exc:
        # Expected only during early bootstrap before the fiscal model is
        # registered. Re-raise anything that is NOT the fiscal module itself, so
        # a genuinely broken import can never silently disable period locks.
        if "fiscal" not in str(exc):
            raise
    else:
        # PeriodClosedError (and any real error) propagates to the caller.
        check_open(session, entry_date, allow_override=allow_closed_period)

    entry = JournalEntry(
        entry_no=entry_no or next_number(session, "JE", entry_date),
        entry_date=entry_date,
        memo=memo,
        source_kind=source_kind,
        source_id=source_id,
        status=DocStatus.POSTED,
        posted_at=datetime.now(),
    )
    for l in line_list:
        if l.debit < 0 or l.credit < 0:
            raise ValueError("Debit/credit values must be non-negative.")
        if (l.debit > 0) and (l.credit > 0):
            raise ValueError("A single line cannot carry both debit and credit.")
        if (l.debit == 0) and (l.credit == 0):
            continue
        entry.lines.append(JournalLine(
            account_id=l.account_id,
            debit=round(l.debit, 2),
            credit=round(l.credit, 2),
            memo=l.memo,
            customer_id=l.customer_id,
            supplier_id=l.supplier_id,
        ))
    session.add(entry)
    session.flush()
    # Defense-in-depth: re-assert balance from the persisted, per-line-rounded
    # amounts. Catches rounding drift across many lines and any future write
    # that reaches the DB bypassing the pre-flush input check above. The
    # session rolls back on this raise (see db.get_session).
    pdr = msum(l.debit for l in entry.lines)
    pcr = msum(l.credit for l in entry.lines)
    if abs(pdr - pcr) > 0.01:
        raise ValueError(
            f"Journal entry unbalanced after persist: DR {pdr:,.2f} != CR {pcr:,.2f}.")
    return entry


def reverse_journal(session: Session, entry: JournalEntry, on: date,
                    memo: Optional[str] = None) -> JournalEntry:
    """Post a reversing entry (debits and credits swapped) for an existing JE."""
    if entry.status != DocStatus.POSTED:
        raise ValueError("Only POSTED entries can be reversed.")
    prior = session.execute(
        select(JournalEntry).where(
            JournalEntry.source_kind == "REVERSAL",
            JournalEntry.source_id == entry.id,
            JournalEntry.status == DocStatus.POSTED,
        )
    ).scalars().first()
    if prior is not None:
        raise ValueError(
            f"{entry.entry_no} has already been reversed ({prior.entry_no}).")
    lines = [JELine(account_id=l.account_id, debit=l.credit, credit=l.debit,
                    memo=l.memo, customer_id=l.customer_id, supplier_id=l.supplier_id)
             for l in entry.lines]
    return post_journal(
        session, on, memo or f"Reversal of {entry.entry_no}", lines,
        source_kind="REVERSAL", source_id=entry.id,
    )


# ---- queries ---------------------------------------------------------------


def account_balance(
    session: Session, account_id: int, *,
    as_of: Optional[date] = None,
    period_start: Optional[date] = None,
) -> float:
    """Net balance for an account, signed per the account's normal side.

    For ASSET/EXPENSE: returns DR - CR (positive = debit balance, the normal side)
    For LIABILITY/EQUITY/INCOME: returns CR - DR (positive = credit balance).
    """
    q = (
        select(
            func.coalesce(func.sum(JournalLine.debit), 0.0),
            func.coalesce(func.sum(JournalLine.credit), 0.0),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.status == DocStatus.POSTED,
        )
    )
    if as_of:
        q = q.where(JournalEntry.entry_date <= as_of)
    if period_start:
        q = q.where(JournalEntry.entry_date >= period_start)
    dr, cr = session.execute(q).one()
    acct = session.get(Account, account_id)
    if acct is None:
        return 0.0
    normal = NORMAL_BALANCE[acct.type]
    return round((dr - cr) if normal == "DR" else (cr - dr), 2)


def trial_balance(session: Session, *, as_of: Optional[date] = None) -> list[dict]:
    """List every postable account with its signed balance.

    Returns one row per account that has nonzero activity. Sum of all
    debit-side balances should equal sum of credit-side balances.
    """
    q = (
        select(
            Account.id, Account.code, Account.name, Account.type,
            func.coalesce(func.sum(JournalLine.debit), 0.0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0.0).label("cr"),
        )
        .join(JournalLine, JournalLine.account_id == Account.id, isouter=True)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id, isouter=True)
        .where(or_(JournalEntry.status == DocStatus.POSTED, JournalEntry.id.is_(None)))
        .group_by(Account.id)
        .order_by(Account.code)
    )
    if as_of:
        q = q.where(or_(JournalEntry.entry_date <= as_of, JournalEntry.id.is_(None)))

    rows: list[dict] = []
    for r in session.execute(q):
        dr, cr = float(r.dr or 0), float(r.cr or 0)
        if dr == 0 and cr == 0:
            continue
        # Net each account onto whichever side it actually lands; the maths is
        # the same regardless of the account's normal balance.
        dr_bal, cr_bal = max(dr - cr, 0), max(cr - dr, 0)
        rows.append({
            "code": r.code, "name": r.name, "type": r.type.value,
            "debit": round(dr_bal, 2), "credit": round(cr_bal, 2),
        })
    return rows


def general_ledger(
    session: Session, account_id: int, *,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> list[dict]:
    """Detail of every posting against an account in date order."""
    q = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.status == DocStatus.POSTED,
        )
        .order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id)
    )
    if period_start:
        q = q.where(JournalEntry.entry_date >= period_start)
    if period_end:
        q = q.where(JournalEntry.entry_date <= period_end)

    rows = []
    running = 0.0
    acct = session.get(Account, account_id)
    normal_dr = NORMAL_BALANCE[acct.type] == "DR" if acct else True
    for line, entry in session.execute(q):
        delta = (line.debit - line.credit) if normal_dr else (line.credit - line.debit)
        running += delta
        rows.append({
            "date": entry.entry_date,
            "entry_no": entry.entry_no,
            "memo": line.memo or entry.memo,
            "debit": line.debit,
            "credit": line.credit,
            "running_balance": round(running, 2),
        })
    return rows
