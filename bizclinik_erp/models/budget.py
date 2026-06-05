"""Budgets + monthly budget lines.

A Budget is a named plan for a fiscal year. Each BudgetLine carries the
planned amount for one (account, month) pair, so a single account can have
up to twelve rows per budget. Variance reporting (services.budget) compares
the summed budget lines for a period against the posted GL actuals.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Budget(Base):
    """A named annual budget. Holds a list of monthly BudgetLines."""
    __tablename__ = "budget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    lines: Mapped[list["BudgetLine"]] = relationship(
        "BudgetLine",
        back_populates="budget",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Budget {self.name} {self.year}>"


class BudgetLine(Base):
    """Planned amount for one (account, month) pair within a budget."""
    __tablename__ = "budget_line"
    __table_args__ = (
        UniqueConstraint("budget_id", "account_id", "month",
                         name="uq_budget_line_budget_account_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    budget_id: Mapped[int] = mapped_column(
        ForeignKey("budget.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    amount: Mapped[float] = mapped_column(Float, default=0.0)

    budget: Mapped["Budget"] = relationship("Budget", back_populates="lines")

    def __repr__(self) -> str:
        return f"<BudgetLine b={self.budget_id} a={self.account_id} m={self.month} {self.amount}>"
