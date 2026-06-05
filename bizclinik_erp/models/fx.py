"""Multi-currency: currency master + exchange-rate history.

Functional (reporting) currency is NGN — the general ledger is ALWAYS in
NGN. A document (invoice / bill) may be *denominated* in a foreign currency;
at posting time its amounts are converted to NGN at the captured `fx_rate`
(NGN per 1 unit of the document currency). When a foreign document is later
settled at a different rate, the difference is booked as a realized FX
gain/loss.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Currency(Base):
    __tablename__ = "currency"
    code: Mapped[str] = mapped_column(String(3), primary_key=True)  # ISO 4217
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), default="")
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Currency {self.code}>"


class ExchangeRate(Base):
    """NGN per 1 unit of `currency_code` on `rate_date`."""
    __tablename__ = "exchange_rate"
    __table_args__ = (
        UniqueConstraint("currency_code", "rate_date", name="uq_fx_currency_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currency.code"), nullable=False, index=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rate: Mapped[float] = mapped_column(Float, nullable=False)  # NGN per 1 unit
    source: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
