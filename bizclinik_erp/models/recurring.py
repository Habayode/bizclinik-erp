"""Recurring transaction templates.

A RecurringTemplate is a saved blueprint for a transaction (sales invoice,
supplier bill, or manual journal entry) that materialises on a recurring
schedule — rent, subscriptions, standing orders, payroll-like accruals.

The service layer (`services.recurring`) walks the table, finds templates
where `next_run_date <= as_of`, calls the matching domain service to
post the txn, then advances `next_run_date` by the template's frequency.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class RecurringKind(str, enum.Enum):
    """Which downstream transaction this template materialises."""
    INVOICE = "INVOICE"   # services.sales.issue_invoice
    BILL = "BILL"         # services.purchase.receive_bill
    JOURNAL = "JOURNAL"   # services.ledger.post_journal


class RecurringFrequency(str, enum.Enum):
    """Schedule cadence. Start simple — extend later if needed."""
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


class RecurringTemplate(Base):
    """A saved blueprint for a recurring txn.

    Kind-specific columns are optional — only the ones relevant to `kind`
    are populated. JOURNAL templates store their lines as JSON in
    `payload_json` since journal structure is variable.
    """
    __tablename__ = "recurring_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[RecurringKind] = mapped_column(Enum(RecurringKind), nullable=False)
    frequency: Mapped[RecurringFrequency] = mapped_column(
        Enum(RecurringFrequency), nullable=False,
    )
    next_run_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # INVOICE fields
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customer.id"))
    # BILL fields
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("supplier.id"))
    expense_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    # Shared line fields for INVOICE + BILL
    line_description: Mapped[Optional[str]] = mapped_column(String(255))
    qty: Mapped[Optional[float]] = mapped_column(Float)
    unit_price: Mapped[Optional[float]] = mapped_column(Float)   # INVOICE
    unit_cost: Mapped[Optional[float]] = mapped_column(Float)    # BILL
    tax_rate: Mapped[Optional[float]] = mapped_column(Float)

    # JOURNAL fields
    memo: Mapped[Optional[str]] = mapped_column(Text)
    payload_json: Mapped[Optional[str]] = mapped_column(Text)

    # Run history
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_run_doc: Mapped[Optional[str]] = mapped_column(String(32))

    customer = relationship("Customer")
    supplier = relationship("Supplier")
    expense_account = relationship("Account")

    def __repr__(self) -> str:
        return (f"<RecurringTemplate {self.code} {self.kind.value} "
                f"every {self.frequency.value} next={self.next_run_date}>")
