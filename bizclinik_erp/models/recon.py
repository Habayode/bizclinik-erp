"""Bank reconciliation models.

A BankStatement is a period (usually a month) of imported activity from a
bank-provided file. Each BankStatementLine is one row from that file and
may be matched 1:1 against a JournalLine in the GL (the bank-side leg of
a receipt / payment / charge / transfer).

Lifecycle:
    DRAFT      — created, lines imported, matching in progress
    RECONCILED — every reconcilable line matched, GL balance ties to statement
    LOCKED     — period locked; no further changes (audit / close)
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, Money


class StatementStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    RECONCILED = "RECONCILED"
    LOCKED = "LOCKED"


class BankStatement(Base):
    """A single bank statement period (e.g. April 2026 for BANK1)."""
    __tablename__ = "bank_statement"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(
        ForeignKey("bank_account.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    opening_balance: Mapped[float] = mapped_column(Money, default=0.0)
    closing_balance: Mapped[float] = mapped_column(Money, default=0.0)
    source_file: Mapped[Optional[str]] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    status: Mapped[StatementStatus] = mapped_column(
        Enum(StatementStatus), default=StatementStatus.DRAFT
    )

    bank_account = relationship("BankAccount")
    lines: Mapped[list["BankStatementLine"]] = relationship(
        "BankStatementLine", back_populates="statement",
        cascade="all, delete-orphan", order_by="BankStatementLine.txn_date",
    )


class BankStatementLine(Base):
    """One row from an imported bank statement.

    Amount sign convention: + is a deposit (money in / credit to our bank),
    − is a withdrawal (money out / debit on the statement). Mirrors what a
    typical Nigerian bank statement (Moniepoint, GTB, FBN) shows.
    """
    __tablename__ = "bank_statement_line"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        ForeignKey("bank_statement.id", ondelete="CASCADE"), nullable=False
    )
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    amount: Mapped[float] = mapped_column(Money, nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(64))
    matched_je_line_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_line.id"), nullable=True
    )
    matched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # User can mark a line as a genuine non-match (e.g. bank-only error
    # that is being disputed) so it stops appearing in the unreconciled
    # bucket without forcing an artificial GL entry.
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    statement: Mapped[BankStatement] = relationship(
        BankStatement, back_populates="lines"
    )
    matched_je_line = relationship("JournalLine")
