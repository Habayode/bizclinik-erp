"""Recurring transactions service.

Walks `RecurringTemplate` rows whose `next_run_date` has arrived, materialises
the corresponding txn (invoice, bill or journal entry), advances the
`next_run_date` by the template's frequency, and stamps run history.

JOURNAL templates store their lines as JSON in `payload_json`. The shape is:
    {"lines": [
        {"account_id": 12, "debit": 10000, "credit": 0, "memo": "rent"},
        {"account_id": 7,  "debit": 0,     "credit": 10000, "memo": "bank"},
    ]}
Either `account_id` or `account_code` is accepted per line — code is looked
up at run time.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    RecurringFrequency,
    RecurringKind,
    RecurringTemplate,
)
from . import purchase as purchase_svc
from . import sales as sales_svc
from .ledger import JELine, post_journal


# ---- date helper -----------------------------------------------------------


def _add_months(d: date, months: int) -> date:
    """Add `months` to `d`, clamping to the last day of the target month.

    Example: Jan 31 + 1 month → Feb 28 (or Feb 29 in a leap year).
    """
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def advance(next_run_date: date, frequency: RecurringFrequency) -> date:
    """Return the next scheduled date after `next_run_date` for `frequency`."""
    if frequency == RecurringFrequency.MONTHLY:
        return _add_months(next_run_date, 1)
    if frequency == RecurringFrequency.QUARTERLY:
        return _add_months(next_run_date, 3)
    if frequency == RecurringFrequency.ANNUAL:
        return _add_months(next_run_date, 12)
    raise ValueError(f"Unknown frequency: {frequency!r}")


# ---- create ----------------------------------------------------------------


def create_template(
    session: Session,
    *,
    kind: RecurringKind,
    code: str,
    name: str,
    frequency: RecurringFrequency,
    next_run_date: date,
    payload: dict,
    end_date: Optional[date] = None,
) -> RecurringTemplate:
    """Create a RecurringTemplate. `payload` keys depend on `kind`:

    INVOICE: customer_id, line_description, qty, unit_price, tax_rate
    BILL:    supplier_id, line_description, qty, unit_cost, tax_rate,
             expense_account_id (optional)
    JOURNAL: memo, lines [{account_id|account_code, debit, credit, memo}]
    """
    tpl = RecurringTemplate(
        code=code, name=name, kind=kind, frequency=frequency,
        next_run_date=next_run_date, end_date=end_date, is_active=True,
    )

    if kind == RecurringKind.INVOICE:
        for k in ("customer_id", "line_description", "qty", "unit_price"):
            if payload.get(k) in (None, ""):
                raise ValueError(f"INVOICE template missing '{k}'.")
        tpl.customer_id = int(payload["customer_id"])
        tpl.line_description = str(payload["line_description"])
        tpl.qty = float(payload["qty"])
        tpl.unit_price = float(payload["unit_price"])
        tpl.tax_rate = float(payload.get("tax_rate", 0.0) or 0.0)

    elif kind == RecurringKind.BILL:
        for k in ("supplier_id", "line_description", "qty", "unit_cost"):
            if payload.get(k) in (None, ""):
                raise ValueError(f"BILL template missing '{k}'.")
        tpl.supplier_id = int(payload["supplier_id"])
        tpl.line_description = str(payload["line_description"])
        tpl.qty = float(payload["qty"])
        tpl.unit_cost = float(payload["unit_cost"])
        tpl.tax_rate = float(payload.get("tax_rate", 0.0) or 0.0)
        if payload.get("expense_account_id"):
            tpl.expense_account_id = int(payload["expense_account_id"])

    elif kind == RecurringKind.JOURNAL:
        lines = payload.get("lines") or []
        if not lines:
            raise ValueError("JOURNAL template requires non-empty 'lines'.")
        tpl.memo = str(payload.get("memo") or name)
        tpl.payload_json = json.dumps({"lines": lines})

    else:
        raise ValueError(f"Unknown kind: {kind!r}")

    session.add(tpl)
    session.flush()
    return tpl


# ---- query -----------------------------------------------------------------


def due_templates(session: Session, *, as_of: date) -> list[RecurringTemplate]:
    """Templates eligible to run on or before `as_of`.

    Active, next_run_date <= as_of, and either no end_date or end_date >= as_of.
    """
    q = (
        select(RecurringTemplate)
        .where(
            RecurringTemplate.is_active.is_(True),
            RecurringTemplate.next_run_date <= as_of,
        )
        .order_by(RecurringTemplate.next_run_date, RecurringTemplate.id)
    )
    rows = session.execute(q).scalars().all()
    return [
        t for t in rows
        if t.end_date is None or t.end_date >= as_of
    ]


# ---- run -------------------------------------------------------------------


def _resolve_account_id(session: Session, line: dict) -> int:
    if "account_id" in line and line["account_id"]:
        return int(line["account_id"])
    code = line.get("account_code")
    if not code:
        raise ValueError("Journal line missing both account_id and account_code.")
    acct = session.execute(
        select(Account).where(Account.code == str(code))
    ).scalar_one_or_none()
    if not acct:
        raise ValueError(f"Account code {code!r} not found.")
    return acct.id


def _materialise(session: Session, tpl: RecurringTemplate, on: date) -> str:
    """Materialise a single template and return the doc number issued."""
    if tpl.kind == RecurringKind.INVOICE:
        inv = sales_svc.issue_invoice(
            session,
            customer_id=tpl.customer_id,
            invoice_date=on,
            lines=[sales_svc.LineInput(
                product_id=None,
                description=tpl.line_description or tpl.name,
                qty=tpl.qty or 0.0,
                unit_price=tpl.unit_price or 0.0,
                tax_rate=tpl.tax_rate or 0.0,
            )],
            notes=f"Recurring template {tpl.code}",
        )
        return inv.number

    if tpl.kind == RecurringKind.BILL:
        bill = purchase_svc.receive_bill(
            session,
            supplier_id=tpl.supplier_id,
            bill_date=on,
            lines=[purchase_svc.POLineInput(
                product_id=None,
                description=tpl.line_description or tpl.name,
                qty=tpl.qty or 0.0,
                unit_cost=tpl.unit_cost or 0.0,
                tax_rate=tpl.tax_rate or 0.0,
                expense_account_id=tpl.expense_account_id,
            )],
            notes=f"Recurring template {tpl.code}",
        )
        return bill.number

    if tpl.kind == RecurringKind.JOURNAL:
        payload = json.loads(tpl.payload_json or "{}")
        raw_lines = payload.get("lines") or []
        je_lines: list[JELine] = []
        for ln in raw_lines:
            je_lines.append(JELine(
                account_id=_resolve_account_id(session, ln),
                debit=float(ln.get("debit") or 0.0),
                credit=float(ln.get("credit") or 0.0),
                memo=ln.get("memo"),
            ))
        je = post_journal(
            session, on,
            tpl.memo or f"Recurring {tpl.code}",
            je_lines,
            source_kind="RECURRING",
            source_id=tpl.id,
        )
        return je.entry_no

    raise ValueError(f"Cannot materialise unknown kind {tpl.kind!r}.")


def run_due(session: Session, *, as_of: date) -> dict:
    """Materialise every due template and advance its schedule.

    Returns `{"materialized": N, "skipped": K, "docs": [...]}`.
    Skipped count includes templates whose materialisation raised — the
    template's `next_run_date` is left untouched so the run can be retried.
    """
    docs: list[str] = []
    materialized = 0
    skipped = 0

    for tpl in due_templates(session, as_of=as_of):
        try:
            doc = _materialise(session, tpl, on=tpl.next_run_date)
        except Exception:
            skipped += 1
            continue
        tpl.last_run_at = datetime.now()
        tpl.last_run_doc = doc
        tpl.next_run_date = advance(tpl.next_run_date, tpl.frequency)
        materialized += 1
        docs.append(doc)
        session.flush()

    return {"materialized": materialized, "skipped": skipped, "docs": docs}
