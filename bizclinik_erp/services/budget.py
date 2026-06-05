"""Budget service: create budgets, set monthly lines, and compute
budget-vs-actual variance against the posted general ledger.

Budget figures are stored per (account, month) in BudgetLine. Actuals come
from the GL via `services.ledger.account_balance`, signed on the account's
normal side, so income/expense budgets compare like-for-like with reported
P&L numbers. Variance is defined as (actual - budget): for an expense
account a positive variance means over-spend; for income a positive variance
means over-performance.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Budget, BudgetLine
from .ledger import account_balance


# ---- mutations -------------------------------------------------------------


def create_budget(session: Session, *, name: str, year: int) -> Budget:
    """Create a new active budget for a fiscal year."""
    budget = Budget(name=name, year=year, is_active=True)
    session.add(budget)
    session.flush()
    return budget


def set_budget_line(
    session: Session, budget_id: int, account_id: int, month: int, amount: float
) -> BudgetLine:
    """Upsert the planned amount for one (account, month) within a budget."""
    if not (1 <= month <= 12):
        raise ValueError(f"month must be 1-12, got {month}")
    line = session.execute(
        select(BudgetLine).where(
            BudgetLine.budget_id == budget_id,
            BudgetLine.account_id == account_id,
            BudgetLine.month == month,
        )
    ).scalar_one_or_none()
    if line is None:
        line = BudgetLine(
            budget_id=budget_id, account_id=account_id,
            month=month, amount=float(amount),
        )
        session.add(line)
    else:
        line.amount = float(amount)
    session.flush()
    return line


def bulk_set(session: Session, budget_id: int, rows: list[dict]) -> int:
    """Upsert many lines at once. Each row: {account_id, month, amount}.

    Returns the number of rows processed.
    """
    count = 0
    for r in rows:
        set_budget_line(
            session, budget_id,
            account_id=int(r["account_id"]),
            month=int(r["month"]),
            amount=float(r.get("amount", 0.0) or 0.0),
        )
        count += 1
    return count


# ---- queries ---------------------------------------------------------------


def _months_in_period(period_start: date, period_end: date) -> set[int]:
    """Set of calendar month numbers (1-12) covered by the period.

    Assumes the period sits within a single budget year; only the month
    component is used to pick BudgetLines.
    """
    if period_end < period_start:
        return set()
    return {m for m in range(period_start.month, period_end.month + 1)}


def budget_vs_actual(
    session: Session, budget_id: int, *,
    period_start: date, period_end: date,
) -> list[dict]:
    """Per budgeted account: budget_total, actual_total, variance, variance_pct.

    BUDGET = sum of this budget's lines for the account whose month falls in
    the period. ACTUAL = account_balance(period_start..period_end), signed on
    the account's normal side. variance = actual - budget. variance_pct =
    (actual - budget) / budget * 100, guarded against divide-by-zero.
    """
    months = _months_in_period(period_start, period_end)

    lines = session.execute(
        select(BudgetLine).where(BudgetLine.budget_id == budget_id)
    ).scalars().all()

    budget_by_account: dict[int, float] = {}
    for ln in lines:
        if ln.month in months:
            budget_by_account[ln.account_id] = (
                budget_by_account.get(ln.account_id, 0.0) + ln.amount
            )

    rows: list[dict] = []
    for account_id, budget_total in budget_by_account.items():
        acct = session.get(Account, account_id)
        if acct is None:
            continue
        actual_total = account_balance(
            session, account_id, period_start=period_start, as_of=period_end
        )
        variance = round(actual_total - budget_total, 2)
        if budget_total:
            variance_pct = round((actual_total - budget_total) / budget_total * 100, 2)
        else:
            variance_pct = 0.0
        rows.append({
            "code": acct.code,
            "name": acct.name,
            "type": acct.type.value,
            "budget_total": round(budget_total, 2),
            "actual_total": round(actual_total, 2),
            "variance": variance,
            "variance_pct": variance_pct,
        })

    rows.sort(key=lambda r: r["code"])
    return rows


def budget_summary(session: Session, budget_id: int) -> dict:
    """Totals across the whole budget (all months), split by account type."""
    lines = session.execute(
        select(BudgetLine).where(BudgetLine.budget_id == budget_id)
    ).scalars().all()

    total = 0.0
    by_type: dict[str, float] = {}
    account_ids: set[int] = set()
    for ln in lines:
        total += ln.amount
        account_ids.add(ln.account_id)
        acct = session.get(Account, ln.account_id)
        if acct is not None:
            by_type[acct.type.value] = by_type.get(acct.type.value, 0.0) + ln.amount

    return {
        "budget_id": budget_id,
        "total_budget": round(total, 2),
        "line_count": len(lines),
        "account_count": len(account_ids),
        "by_type": {k: round(v, 2) for k, v in by_type.items()},
    }
