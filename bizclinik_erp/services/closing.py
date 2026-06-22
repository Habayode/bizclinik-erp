"""Month-End Close + Accrual helpers.

Templated adjusting journal entries (accruals, prepaid amortisation, deferred
revenue) plus a computed close checklist. Every posting goes through
`services.ledger.post_journal` so the standard balance/period-close validation
applies. Each helper returns the JournalEntry it created.

Account codes used (from services.seed defaults):
    2160  Accrued Expenses   (LIABILITY) — accrual + deferred-revenue holding
    1170  Prepaid Expenses   (ASSET)     — prepaid amortisation
    4100  Sales              (INCOME)    — revenue deferral / recognition
    2170  Deferred Revenue   (LIABILITY) — preferred holding account if present;
                                          falls back to 2160 when not seeded.
"""
from __future__ import annotations
from ..money import msum

import calendar
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    DocStatus,
    JournalEntry,
)
from .ledger import JELine, post_journal, reverse_journal, trial_balance


# ---- account lookup -------------------------------------------------------


def _acct(session: Session, code: str) -> Account:
    """Resolve an Account by its code. Raises if missing."""
    acct = session.execute(
        select(Account).where(Account.code == code)
    ).scalar_one_or_none()
    if acct is None:
        raise ValueError(f"Account with code {code!r} not found in chart of accounts.")
    return acct


def _deferred_revenue_account(session: Session) -> Account:
    """Holding account for deferred revenue. Prefer a dedicated 2170 Deferred
    Revenue liability if it has been seeded; otherwise fall back to 2160
    Accrued Expenses so the entry still balances on a sensible liability."""
    acct = session.execute(
        select(Account).where(Account.code == "2170")
    ).scalar_one_or_none()
    return acct if acct is not None else _acct(session, "2160")


# ---- adjusting entries ----------------------------------------------------


def accrue_expense(session: Session, *, on: date, amount: float,
                   expense_account_id: int, memo: str) -> JournalEntry:
    """Accrue an expense not yet billed: DR expense / CR Accrued Expenses (2160)."""
    accrued = _acct(session, "2160")
    return post_journal(
        session, on, memo,
        [
            JELine(account_id=expense_account_id, debit=amount, memo=memo),
            JELine(account_id=accrued.id, credit=amount, memo=memo),
        ],
        source_kind="ACCRUAL",
    )


def reverse_accrual(session: Session, *, accrual_je_id: int, on: date) -> JournalEntry:
    """Reverse a prior accrual JE (debits/credits swapped) on `on`."""
    entry = session.get(JournalEntry, accrual_je_id)
    if entry is None:
        raise ValueError(f"Journal entry id {accrual_je_id} not found.")
    return reverse_journal(session, entry, on,
                           memo=f"Reversal of accrual {entry.entry_no}")


def amortize_prepaid(session: Session, *, on: date, amount: float,
                     expense_account_id: int, memo: str) -> JournalEntry:
    """Amortise a prepaid: DR expense / CR Prepaid Expenses (1170)."""
    prepaid = _acct(session, "1170")
    return post_journal(
        session, on, memo,
        [
            JELine(account_id=expense_account_id, debit=amount, memo=memo),
            JELine(account_id=prepaid.id, credit=amount, memo=memo),
        ],
        source_kind="PREPAID_AMORT",
    )


def defer_revenue(session: Session, *, on: date, amount: float,
                  memo: str) -> JournalEntry:
    """Defer revenue already booked to Sales: DR Sales (4100) / CR a deferred
    revenue liability (2170 if present, else 2160 Accrued Expenses)."""
    sales = _acct(session, "4100")
    holding = _deferred_revenue_account(session)
    return post_journal(
        session, on, memo,
        [
            JELine(account_id=sales.id, debit=amount, memo=memo),
            JELine(account_id=holding.id, credit=amount, memo=memo),
        ],
        source_kind="REVENUE_DEFERRAL",
    )


def recognize_deferred_revenue(session: Session, *, on: date, amount: float,
                               memo: str) -> JournalEntry:
    """Recognise previously deferred revenue: DR deferred-revenue liability /
    CR Sales (4100). The mirror image of `defer_revenue`."""
    sales = _acct(session, "4100")
    holding = _deferred_revenue_account(session)
    return post_journal(
        session, on, memo,
        [
            JELine(account_id=holding.id, debit=amount, memo=memo),
            JELine(account_id=sales.id, credit=amount, memo=memo),
        ],
        source_kind="REVENUE_RECOGNITION",
    )


# ---- close checklist ------------------------------------------------------


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    _, last = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last)


def close_checklist(session: Session, *, year: int, month: int) -> list[dict]:
    """Compute the month-end close checklist for a period from the DB.

    Returns a list of {task, status, detail} dicts where status is one of
    'ok' | 'pending' | 'na'.
    """
    start, end = _month_bounds(year, month)
    items: list[dict] = []

    # 1. All invoices posted (no DRAFT SalesInvoice in the month).
    from ..models import SalesInvoice
    draft_inv = session.execute(
        select(SalesInvoice).where(
            SalesInvoice.invoice_date >= start,
            SalesInvoice.invoice_date <= end,
            SalesInvoice.status == DocStatus.DRAFT,
        )
    ).scalars().all()
    items.append({
        "task": "All invoices posted",
        "status": "ok" if not draft_inv else "pending",
        "detail": "No draft invoices" if not draft_inv
                  else f"{len(draft_inv)} draft invoice(s) outstanding",
    })

    # 2. All bills posted (no DRAFT Bill in the month).
    from ..models import Bill
    draft_bills = session.execute(
        select(Bill).where(
            Bill.bill_date >= start,
            Bill.bill_date <= end,
            Bill.status == DocStatus.DRAFT,
        )
    ).scalars().all()
    items.append({
        "task": "All bills posted",
        "status": "ok" if not draft_bills else "pending",
        "detail": "No draft bills" if not draft_bills
                  else f"{len(draft_bills)} draft bill(s) outstanding",
    })

    # 3. Depreciation run — only relevant if FixedAsset table has rows.
    from ..models import FixedAsset
    has_assets = session.execute(select(FixedAsset.id).limit(1)).first() is not None
    if not has_assets:
        items.append({
            "task": "Depreciation run",
            "status": "na",
            "detail": "No fixed assets on file",
        })
    else:
        dep_je = session.execute(
            select(JournalEntry).where(
                JournalEntry.entry_date >= start,
                JournalEntry.entry_date <= end,
                JournalEntry.source_kind == "DEPRECIATION",
            ).limit(1)
        ).scalar_one_or_none()
        items.append({
            "task": "Depreciation run",
            "status": "ok" if dep_je is not None else "pending",
            "detail": "Depreciation JE found" if dep_je is not None
                      else "No depreciation JE this month",
        })

    # 4. Bank reconciled — guard the recon tables behind try/except import.
    try:
        from ..models import BankStatement, StatementStatus
        recon = session.execute(
            select(BankStatement).where(
                BankStatement.period_end >= start,
                BankStatement.period_start <= end,
                BankStatement.status == StatementStatus.RECONCILED,
            ).limit(1)
        ).scalar_one_or_none()
        items.append({
            "task": "Bank reconciled",
            "status": "ok" if recon is not None else "pending",
            "detail": "Reconciled statement found" if recon is not None
                      else "No reconciled statement this month",
        })
    except Exception:
        items.append({
            "task": "Bank reconciled",
            "status": "na",
            "detail": "Reconciliation module unavailable",
        })

    # 5. Trial balance balances.
    tb = trial_balance(session, as_of=end)
    tot_dr = msum(r["debit"] for r in tb)
    tot_cr = msum(r["credit"] for r in tb)
    balanced = abs(tot_dr - tot_cr) < 0.01
    items.append({
        "task": "Trial balance balances",
        "status": "ok" if balanced else "pending",
        "detail": f"DR {tot_dr:,.2f} vs CR {tot_cr:,.2f}",
    })

    # 6. Period closed (FiscalPeriod status != OPEN).
    from ..models import FiscalPeriod, PeriodStatus
    period = session.execute(
        select(FiscalPeriod).where(
            FiscalPeriod.year == year, FiscalPeriod.month == month
        )
    ).scalar_one_or_none()
    if period is None or period.status == PeriodStatus.OPEN:
        items.append({
            "task": "Period closed",
            "status": "pending",
            "detail": "Period is OPEN" if period else "Period not yet created",
        })
    else:
        items.append({
            "task": "Period closed",
            "status": "ok",
            "detail": f"Period is {period.status.value}",
        })

    return items
