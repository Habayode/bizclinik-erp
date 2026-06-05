"""Foreign-exchange service: currencies, rates, conversion, realized FX.

Functional currency is NGN. `rate` everywhere means **NGN per 1 unit** of the
foreign currency. NGN itself always has rate 1.0.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Account, Currency, ExchangeRate
from ..models.audit import AuditAction
from .audit import record


BASE_CURRENCY = "NGN"
FX_GAINLOSS_CODE = "4300"


def list_currencies(session: Session, *, active_only: bool = True) -> list[Currency]:
    q = select(Currency).order_by(Currency.code)
    if active_only:
        q = q.where(Currency.is_active == True)  # noqa: E712
    return list(session.execute(q).scalars())


def set_rate(session: Session, currency_code: str, rate_date: date, rate: float,
             *, source: Optional[str] = None, user_id: Optional[int] = None) -> ExchangeRate:
    """Upsert an exchange rate (NGN per 1 unit of currency_code)."""
    currency_code = currency_code.upper()
    if currency_code == BASE_CURRENCY:
        raise ValueError("The base currency (NGN) always has rate 1.0.")
    if rate <= 0:
        raise ValueError("Rate must be positive.")
    existing = session.execute(
        select(ExchangeRate).where(
            ExchangeRate.currency_code == currency_code,
            ExchangeRate.rate_date == rate_date,
        )
    ).scalar_one_or_none()
    if existing:
        existing.rate = rate
        existing.source = source
        er = existing
    else:
        er = ExchangeRate(currency_code=currency_code, rate_date=rate_date,
                          rate=rate, source=source)
        session.add(er)
    session.flush()
    record(session, action=AuditAction.UPDATE, entity_type="exchange_rate",
           entity_id=er.id,
           description=f"Set {currency_code} rate on {rate_date} = {rate}",
           user_id=user_id, source="services.fx")
    return er


def get_rate(session: Session, currency_code: str, *,
             as_of: Optional[date] = None) -> float:
    """Latest rate on/before `as_of` (NGN per 1 unit). NGN returns 1.0.
    Raises if no rate is on file for a foreign currency."""
    currency_code = (currency_code or BASE_CURRENCY).upper()
    if currency_code == BASE_CURRENCY:
        return 1.0
    q = select(ExchangeRate).where(ExchangeRate.currency_code == currency_code)
    if as_of:
        q = q.where(ExchangeRate.rate_date <= as_of)
    q = q.order_by(desc(ExchangeRate.rate_date))
    er = session.execute(q).scalars().first()
    if not er:
        raise ValueError(
            f"No exchange rate on file for {currency_code}"
            + (f" on/before {as_of}" if as_of else "")
            + ". Add one on the Currencies page first."
        )
    return er.rate


def to_ngn(amount: float, fx_rate: float) -> float:
    """Convert a foreign amount to NGN."""
    return round(amount * fx_rate, 2)


def resolve_rate(session: Session, currency_code: str, *,
                 fx_rate: Optional[float] = None,
                 as_of: Optional[date] = None) -> float:
    """If `fx_rate` is given use it; else look up the latest. NGN -> 1.0."""
    code = (currency_code or BASE_CURRENCY).upper()
    if code == BASE_CURRENCY:
        return 1.0
    if fx_rate is not None:
        if fx_rate <= 0:
            raise ValueError("fx_rate must be positive.")
        return fx_rate
    return get_rate(session, code, as_of=as_of)


def fx_gainloss_account_id(session: Session) -> int:
    acct = session.execute(
        select(Account).where(Account.code == FX_GAINLOSS_CODE)
    ).scalar_one_or_none()
    if not acct:
        raise RuntimeError("FX Gain/Loss account (4300) missing — seed defaults.")
    return acct.id


# --------------------------------------------------------------------------- #
# Unrealized FX revaluation (period-end)                                       #
# --------------------------------------------------------------------------- #

def unrealized_fx_revaluation(session: Session, *, as_of: Optional[date] = None) -> dict:
    """Mark open foreign-currency receivables and payables to the period-end rate.

    For every open (not fully settled) foreign-denominated sales invoice and
    bill, compare the NGN value booked at the document's issue rate against the
    NGN value at the ``as_of`` rate. The difference is an *unrealized* FX
    gain/loss — it has not been cashed in yet, so this is a report (no journal
    entry is posted; period-end revaluation entries are typically reversing and
    are left to the accountant to book/reverse).

    Sign convention (impact on profit):
      • Receivable (asset):  gain when NGN weakens (rate up)  -> +outstanding*(cur-book)
      • Payable (liability): loss when NGN weakens (rate up)  -> -outstanding*(cur-book)

    Returns::
        {
          "as_of": date|None,
          "receivables": [ {doc..., outstanding_fc, booked_rate, current_rate,
                            booked_ngn, current_ngn, unrealized} , ... ],
          "payables":    [ ... ],
          "net_unrealized": float,   # +gain / -loss to P&L
          "skipped": [ {scope, ref, reason} ]   # e.g. no rate on file
        }
    """
    from ..models import Bill, SalesInvoice
    from ..models.txn import DocStatus

    open_states = {DocStatus.POSTED, DocStatus.PARTIAL}

    receivables: list[dict] = []
    payables: list[dict] = []
    skipped: list[dict] = []

    def _line(scope, doc, outstanding_fc, booked_rate, current_rate, sign):
        booked_ngn = round(outstanding_fc * booked_rate, 2)
        current_ngn = round(outstanding_fc * current_rate, 2)
        unrealized = round(sign * (current_ngn - booked_ngn), 2)
        return {
            "scope": scope,
            "ref": doc.number,
            "currency": doc.currency_code,
            "outstanding_fc": round(outstanding_fc, 2),
            "booked_rate": round(booked_rate, 6),
            "current_rate": round(current_rate, 6),
            "booked_ngn": booked_ngn,
            "current_ngn": current_ngn,
            "unrealized": unrealized,
        }

    # Receivables (sales invoices) — asset, sign +1.
    for inv in session.execute(select(SalesInvoice)).scalars():
        if (inv.currency_code or BASE_CURRENCY).upper() == BASE_CURRENCY:
            continue
        if inv.status not in open_states:
            continue
        outstanding = round(inv.grand_total - (inv.amount_paid or 0.0), 2)
        if outstanding <= 0:
            continue
        try:
            cur = get_rate(session, inv.currency_code, as_of=as_of)
        except ValueError as exc:
            skipped.append({"scope": "receivable", "ref": inv.number, "reason": str(exc)})
            continue
        receivables.append(_line("receivable", inv, outstanding, inv.fx_rate or 1.0, cur, +1))

    # Payables (bills) — liability, sign -1.
    for bill in session.execute(select(Bill)).scalars():
        if (bill.currency_code or BASE_CURRENCY).upper() == BASE_CURRENCY:
            continue
        if bill.status not in open_states:
            continue
        outstanding = round(bill.grand_total - (bill.amount_paid or 0.0), 2)
        if outstanding <= 0:
            continue
        try:
            cur = get_rate(session, bill.currency_code, as_of=as_of)
        except ValueError as exc:
            skipped.append({"scope": "payable", "ref": bill.number, "reason": str(exc)})
            continue
        payables.append(_line("payable", bill, outstanding, bill.fx_rate or 1.0, cur, -1))

    net = round(sum(r["unrealized"] for r in receivables)
                + sum(p["unrealized"] for p in payables), 2)
    return {
        "as_of": as_of,
        "receivables": receivables,
        "payables": payables,
        "net_unrealized": net,
        "skipped": skipped,
    }
