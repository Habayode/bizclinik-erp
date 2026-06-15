"""Bank reconciliation service.

Reconciliation here is the classic "tick-and-tie" between rows on the bank
statement and lines on the GL bank account. Each statement line either
matches a GL bank-side journal line or is excluded (genuine non-match).

Sign convention:
    statement_line.amount  > 0  → deposit (bank statement credit)
    statement_line.amount  < 0  → withdrawal (bank statement debit)
    journal_line.debit     > 0  → cash IN to our bank GL  ⇒ matches deposit
    journal_line.credit    > 0  → cash OUT of our bank GL ⇒ matches withdrawal

So a statement deposit of +50,000 should match a GL line with
debit − credit ≈ +50,000 on the bank GL account.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    DocStatus,
    JournalEntry,
    JournalLine,
    StatementStatus,
)


# ---- statement lifecycle ---------------------------------------------------


def create_statement(
    session: Session,
    *,
    bank_account_id: int,
    period_start: date,
    period_end: date,
    opening_balance: float,
    closing_balance: float,
    source_file: str,
) -> BankStatement:
    """Create a DRAFT statement for the given bank + period."""
    authz.require_perm("manage.banks")
    bank = session.get(BankAccount, bank_account_id)
    if not bank:
        raise ValueError(f"Bank account {bank_account_id} not found.")
    if period_end < period_start:
        raise ValueError("period_end must be on or after period_start.")
    stmt = BankStatement(
        bank_account_id=bank_account_id,
        period_start=period_start,
        period_end=period_end,
        opening_balance=round(float(opening_balance), 2),
        closing_balance=round(float(closing_balance), 2),
        source_file=source_file,
        imported_at=datetime.utcnow(),
        status=StatementStatus.DRAFT,
    )
    session.add(stmt)
    session.flush()
    return stmt


def import_statement_lines(
    session: Session, statement_id: int, rows: Iterable[dict],
) -> int:
    """Bulk-insert rows as BankStatementLine records. Returns row count."""
    authz.require_perm("manage.banks")
    stmt = session.get(BankStatement, statement_id)
    if not stmt:
        raise ValueError(f"Statement {statement_id} not found.")
    if stmt.status == StatementStatus.LOCKED:
        raise ValueError("Cannot import lines into a LOCKED statement.")

    count = 0
    for r in rows:
        amt = round(float(r.get("amount", 0.0)), 2)
        if amt == 0.0:
            continue
        line = BankStatementLine(
            statement_id=statement_id,
            txn_date=r["txn_date"],
            description=(r.get("description") or "")[:512],
            amount=amt,
            reference=(r.get("reference") or "")[:64] or None,
        )
        session.add(line)
        count += 1
    session.flush()
    return count


# ---- matching --------------------------------------------------------------


def _unmatched_gl_lines(
    session: Session, *, bank_gl_account_id: int,
    period_start: date, period_end: date, day_tolerance: int,
) -> list[tuple[JournalLine, JournalEntry]]:
    """All POSTED bank-side JE lines in (or near) the statement period that
    are not already matched to some other statement line."""
    # Already-matched statement_line.matched_je_line_id values:
    matched_subq = (
        select(BankStatementLine.matched_je_line_id)
        .where(BankStatementLine.matched_je_line_id.is_not(None))
    )
    # Expand the JE window by the day tolerance so cross-period matches still work.
    from datetime import timedelta
    win_start = period_start - timedelta(days=day_tolerance)
    win_end = period_end + timedelta(days=day_tolerance)

    q = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == bank_gl_account_id,
            JournalEntry.status == DocStatus.POSTED,
            JournalEntry.entry_date >= win_start,
            JournalEntry.entry_date <= win_end,
            JournalLine.id.not_in(matched_subq),
        )
        .order_by(JournalEntry.entry_date, JournalLine.id)
    )
    return list(session.execute(q).all())


def auto_match(
    session: Session, statement_id: int, *, day_tolerance: int = 3,
) -> dict:
    """Greedy 1:1 match: amount within ₦0.01, date within ±day_tolerance.

    Walks unmatched statement lines in date order and takes the first
    eligible GL line. Cheap and correct enough for typical SME volumes;
    a smarter optimiser is unnecessary unless there are collisions.
    """
    stmt = session.get(BankStatement, statement_id)
    if not stmt:
        raise ValueError(f"Statement {statement_id} not found.")
    bank = session.get(BankAccount, stmt.bank_account_id)
    if not bank:
        raise ValueError("Bank account behind statement is missing.")

    gl_pool = _unmatched_gl_lines(
        session,
        bank_gl_account_id=bank.gl_account_id,
        period_start=stmt.period_start,
        period_end=stmt.period_end,
        day_tolerance=day_tolerance,
    )

    # Index GL lines by (signed_amount) for quick lookup. Each entry tracks
    # whether it's been claimed in this run.
    pool: list[dict] = []
    for jl, je in gl_pool:
        signed = round(jl.debit - jl.credit, 2)
        if signed == 0.0:
            continue
        pool.append({
            "jl": jl, "je": je, "signed": signed, "claimed": False,
        })

    matched = 0
    unmatched_stmt = 0
    now = datetime.utcnow()

    stmt_lines = sorted(
        [l for l in stmt.lines
         if l.matched_je_line_id is None and not l.is_excluded],
        key=lambda x: x.txn_date,
    )

    for sl in stmt_lines:
        target = round(sl.amount, 2)
        best_idx = -1
        best_day_diff = None
        for idx, cand in enumerate(pool):
            if cand["claimed"]:
                continue
            if abs(cand["signed"] - target) > 0.01:
                continue
            day_diff = abs((cand["je"].entry_date - sl.txn_date).days)
            if day_diff > day_tolerance:
                continue
            if best_day_diff is None or day_diff < best_day_diff:
                best_idx = idx
                best_day_diff = day_diff
                if day_diff == 0:
                    break
        if best_idx >= 0:
            cand = pool[best_idx]
            cand["claimed"] = True
            sl.matched_je_line_id = cand["jl"].id
            sl.matched_at = now
            matched += 1
        else:
            unmatched_stmt += 1

    unmatched_gl = sum(1 for c in pool if not c["claimed"])
    session.flush()
    return {
        "matched": matched,
        "unmatched_statement": unmatched_stmt,
        "unmatched_gl": unmatched_gl,
    }


def manual_match(
    session: Session, statement_line_id: int, je_line_id: int,
) -> BankStatementLine:
    """Force a match between a statement line and a specific JE line."""
    sl = session.get(BankStatementLine, statement_line_id)
    if not sl:
        raise ValueError(f"Statement line {statement_line_id} not found.")
    jl = session.get(JournalLine, je_line_id)
    if not jl:
        raise ValueError(f"Journal line {je_line_id} not found.")
    # Guard: another statement line shouldn't already own this JE line.
    already = session.execute(
        select(BankStatementLine).where(
            BankStatementLine.matched_je_line_id == je_line_id,
            BankStatementLine.id != statement_line_id,
        )
    ).scalar_one_or_none()
    if already is not None:
        raise ValueError(
            f"Journal line {je_line_id} is already matched to statement "
            f"line {already.id}."
        )
    sl.matched_je_line_id = je_line_id
    sl.matched_at = datetime.utcnow()
    sl.is_excluded = False
    session.flush()
    return sl


def unmatch(session: Session, statement_line_id: int) -> BankStatementLine:
    sl = session.get(BankStatementLine, statement_line_id)
    if not sl:
        raise ValueError(f"Statement line {statement_line_id} not found.")
    sl.matched_je_line_id = None
    sl.matched_at = None
    session.flush()
    return sl


# ---- summary + finalize ----------------------------------------------------


def reconciliation_summary(session: Session, statement_id: int) -> dict:
    """Totals for a statement in progress.

    gl_balance              — sum of signed bank-GL movement (DR − CR) over the period
    statement_balance       — closing − opening on the statement itself
    matched_total           — sum of matched statement amounts
    unreconciled_*_total    — leftover bucket totals
    computed_diff           — closing − (opening + sum of matched_total) = how far
                              off the statement is once matches are applied
    """
    stmt = session.get(BankStatement, statement_id)
    if not stmt:
        raise ValueError(f"Statement {statement_id} not found.")
    bank = session.get(BankAccount, stmt.bank_account_id)

    # GL movement on the bank account over the period.
    q = (
        select(
            func.coalesce(func.sum(JournalLine.debit), 0.0),
            func.coalesce(func.sum(JournalLine.credit), 0.0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == bank.gl_account_id,
            JournalEntry.status == DocStatus.POSTED,
            JournalEntry.entry_date >= stmt.period_start,
            JournalEntry.entry_date <= stmt.period_end,
        )
    )
    dr, cr = session.execute(q).one()
    gl_movement = round(float(dr) - float(cr), 2)

    matched_total = 0.0
    unreconciled_stmt_total = 0.0
    matched_count = 0
    unmatched_count = 0
    for l in stmt.lines:
        if l.matched_je_line_id is not None:
            matched_total += l.amount
            matched_count += 1
        elif not l.is_excluded:
            unreconciled_stmt_total += l.amount
            unmatched_count += 1

    # Unreconciled GL = bank-side JE lines in window that no statement line claims.
    matched_je_ids = [l.matched_je_line_id for l in stmt.lines
                      if l.matched_je_line_id is not None]
    q2 = (
        select(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == bank.gl_account_id,
            JournalEntry.status == DocStatus.POSTED,
            JournalEntry.entry_date >= stmt.period_start,
            JournalEntry.entry_date <= stmt.period_end,
        )
    )
    if matched_je_ids:
        q2 = q2.where(JournalLine.id.not_in(matched_je_ids))
    unreconciled_gl_total = 0.0
    unreconciled_gl_count = 0
    for jl in session.execute(q2).scalars():
        unreconciled_gl_total += round(jl.debit - jl.credit, 2)
        unreconciled_gl_count += 1

    statement_balance_delta = round(
        stmt.closing_balance - stmt.opening_balance, 2
    )
    computed_diff = round(
        statement_balance_delta - matched_total
        - unreconciled_stmt_total, 2
    )
    return {
        "statement_id": stmt.id,
        "status": stmt.status.value,
        "gl_balance": gl_movement,
        "statement_balance": statement_balance_delta,
        "opening_balance": stmt.opening_balance,
        "closing_balance": stmt.closing_balance,
        "matched_total": round(matched_total, 2),
        "matched_count": matched_count,
        "unreconciled_statement_total": round(unreconciled_stmt_total, 2),
        "unreconciled_statement_count": unmatched_count,
        "unreconciled_gl_total": round(unreconciled_gl_total, 2),
        "unreconciled_gl_count": unreconciled_gl_count,
        "computed_diff": computed_diff,
    }


def finalize(session: Session, statement_id: int) -> BankStatement:
    """Mark statement RECONCILED. Caller should ensure unreconciled buckets are empty."""
    stmt = session.get(BankStatement, statement_id)
    if not stmt:
        raise ValueError(f"Statement {statement_id} not found.")
    if stmt.status == StatementStatus.LOCKED:
        raise ValueError("Statement is LOCKED and cannot be re-finalised.")
    stmt.status = StatementStatus.RECONCILED
    session.flush()
    return stmt
