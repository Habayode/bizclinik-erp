"""Master data: company, chart of accounts, customers, suppliers, products, etc."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


# ---- Chart of Accounts -----------------------------------------------------


class AccountType(str, enum.Enum):
    """Top-level GL classification. Determines normal balance + report bucket."""
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


# Maps each AccountType to its normal balance side. Used to sign-check ledger
# balances when producing reports.
NORMAL_BALANCE = {
    AccountType.ASSET: "DR",
    AccountType.EXPENSE: "DR",
    AccountType.LIABILITY: "CR",
    AccountType.EQUITY: "CR",
    AccountType.INCOME: "CR",
}


class Company(Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rc_number: Mapped[Optional[str]] = mapped_column(String(64))
    address: Mapped[Optional[str]] = mapped_column(String(512))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    vat_number: Mapped[Optional[str]] = mapped_column(String(64))
    # Tax Identification Number (FIRS/JTB) — distinct from the CAC RC number.
    tin: Mapped[Optional[str]] = mapped_column(String(64))
    # FIRS-assigned Service ID used as the middle segment of the IRN. Empty
    # until the business is onboarded to the FIRS MBS e-invoicing platform.
    firs_service_id: Mapped[Optional[str]] = mapped_column(String(32))
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1)
    # Industry vertical that tailors the UI: "school" gives a school-first,
    # curated navigation; "general" (default) is the standard accounting ERP.
    vertical: Mapped[str] = mapped_column(String(24), default="general")


class Account(Base):
    """Chart of Accounts node. Hierarchical via parent_id."""
    __tablename__ = "account"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    is_postable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    parent: Mapped[Optional["Account"]] = relationship(
        "Account", remote_side=lambda: [Account.id], back_populates="children"
    )
    children: Mapped[list["Account"]] = relationship(
        "Account", back_populates="parent"
    )

    def __repr__(self) -> str:
        return f"<Account {self.code} {self.name}>"


class TaxCode(Base):
    """A tax rate + the GL accounts it posts to."""
    __tablename__ = "tax_code"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    output_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    input_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))

    output_account: Mapped[Optional[Account]] = relationship(foreign_keys=[output_account_id])
    input_account: Mapped[Optional[Account]] = relationship(foreign_keys=[input_account_id])


# ---- Trading partners ------------------------------------------------------


class Customer(Base):
    __tablename__ = "customer"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    address: Mapped[Optional[str]] = mapped_column(String(512))
    receivable_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    credit_limit: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    receivable_account: Mapped[Optional[Account]] = relationship()


class Supplier(Base):
    __tablename__ = "supplier"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    address: Mapped[Optional[str]] = mapped_column(String(512))
    payable_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    payable_account: Mapped[Optional[Account]] = relationship()


# ---- Inventory -------------------------------------------------------------


class Warehouse(Base):
    __tablename__ = "warehouse"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "product"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512))
    unit: Mapped[str] = mapped_column(String(16), default="ea")
    standard_price: Mapped[float] = mapped_column(Float, default=0.0)
    standard_cost: Mapped[float] = mapped_column(Float, default=0.0)
    # Running weighted-average cost — updated by inventory.service on receipt.
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)
    qty_on_hand: Mapped[float] = mapped_column(Float, default=0.0)
    reorder_level: Mapped[float] = mapped_column(Float, default=0.0)
    is_stockable: Mapped[bool] = mapped_column(Boolean, default=True)
    inventory_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    income_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    cogs_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))
    tax_code_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tax_code.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    inventory_account: Mapped[Optional[Account]] = relationship(foreign_keys=[inventory_account_id])
    income_account: Mapped[Optional[Account]] = relationship(foreign_keys=[income_account_id])
    cogs_account: Mapped[Optional[Account]] = relationship(foreign_keys=[cogs_account_id])
    tax_code: Mapped[Optional[TaxCode]] = relationship()


# ---- Banking + HR ----------------------------------------------------------


class BankAccount(Base):
    __tablename__ = "bank_account"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank: Mapped[Optional[str]] = mapped_column(String(128))
    account_number: Mapped[Optional[str]] = mapped_column(String(64))
    gl_account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    opening_balance: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    gl_account: Mapped[Account] = relationship()


class Employee(Base):
    __tablename__ = "employee"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    monthly_gross: Mapped[float] = mapped_column(Float, default=0.0)
    paye_rate: Mapped[float] = mapped_column(Float, default=0.0)
    pension_rate: Mapped[float] = mapped_column(Float, default=0.08)  # 8% employee
    pension_employer_rate: Mapped[float] = mapped_column(Float, default=0.10)
    hire_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # HR fields (added with the HR module).
    department: Mapped[Optional[str]] = mapped_column(String(120))
    job_title: Mapped[Optional[str]] = mapped_column(String(120))
    employment_type: Mapped[Optional[str]] = mapped_column(String(40))  # full-time, contract…
    annual_leave_days: Mapped[float] = mapped_column(Float, default=20.0)
