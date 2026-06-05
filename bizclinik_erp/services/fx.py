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
