"""Transactional models: GL entries, sales cycle, purchase cycle, stock, payroll."""
from __future__ import annotations
from ..money import msum

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class DocStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"        # GL impact recorded
    PARTIAL = "PARTIAL"      # Partially paid / received
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class DocCounter(Base):
    """Atomic per-(doc kind, year) sequence backing services.numbering. One row
    per key such as 'INV-2026'. next_number() does an atomic
    ``UPDATE ... SET value = value + 1 RETURNING value`` so two concurrent posts
    can never read the same max() and collide on a document number."""
    __tablename__ = "doc_counter"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ---- General Ledger -------------------------------------------------------


class JournalEntry(Base):
    """A balanced set of debits/credits — the atomic unit of bookkeeping.

    All financial activity in the ERP eventually becomes a JournalEntry. Every
    line under a posted JE has DR or CR; sum(DR) == sum(CR) is enforced at
    post time (see services.ledger.post_journal).
    """
    __tablename__ = "journal_entry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text)
    source_kind: Mapped[Optional[str]] = mapped_column(String(32))  # 'INVOICE','BILL',...
    source_id: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine", back_populates="entry",
        cascade="all, delete-orphan", order_by="JournalLine.id",
    )

    @property
    def total_debit(self) -> float:
        return msum(l.debit for l in self.lines)

    @property
    def total_credit(self) -> float:
        return msum(l.credit for l in self.lines)

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_debit - self.total_credit) < 0.01


class JournalLine(Base):
    __tablename__ = "journal_line"
    # Database-level backstop for the double-entry invariants that
    # services.ledger.post_journal enforces in Python: amounts are non-negative
    # and a line is single-sided. (DR==CR is a cross-row aggregate and is
    # re-asserted in post_journal after flush.) Applies to all freshly created
    # databases; existing SQLite tables keep the Python guard.
    __table_args__ = (
        CheckConstraint("debit >= 0", name="ck_journal_line_debit_nonneg"),
        CheckConstraint("credit >= 0", name="ck_journal_line_credit_nonneg"),
        CheckConstraint("NOT (debit > 0 AND credit > 0)",
                        name="ck_journal_line_single_sided"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    debit: Mapped[float] = mapped_column(Float, default=0.0)
    credit: Mapped[float] = mapped_column(Float, default=0.0)
    memo: Mapped[Optional[str]] = mapped_column(String(255))
    # Optional contact pointers for AR/AP sub-ledger inquiry.
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customer.id"))
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("supplier.id"))

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


# ---- Sales cycle ----------------------------------------------------------


class Quotation(Base):
    __tablename__ = "quotation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)

    customer: Mapped["Customer"] = relationship()  # type: ignore[name-defined]
    lines: Mapped[list["QuotationLine"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan",
        order_by="QuotationLine.id",
    )

    @property
    def subtotal(self) -> float:
        return msum(l.subtotal for l in self.lines)

    @property
    def tax_total(self) -> float:
        return msum(l.tax_amount for l in self.lines)

    @property
    def grand_total(self) -> float:
        return round(self.subtotal + self.tax_total, 2)


class QuotationLine(Base):
    __tablename__ = "quotation_line"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("product.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)

    quotation: Mapped[Quotation] = relationship(back_populates="lines")
    product = relationship("Product")

    @property
    def subtotal(self) -> float:
        return round(self.qty * self.unit_price, 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax_amount, 2)


class SalesOrder(Base):
    __tablename__ = "sales_order"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False)
    quotation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("quotation.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)

    customer = relationship("Customer")
    quotation = relationship("Quotation")
    lines: Mapped[list["SalesOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
        order_by="SalesOrderLine.id",
    )


class SalesOrderLine(Base):
    __tablename__ = "sales_order_line"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("sales_order.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("product.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped[SalesOrder] = relationship(back_populates="lines")
    product = relationship("Product")


class SalesInvoice(Base):
    __tablename__ = "sales_invoice"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False)
    sales_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales_order.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0)
    je_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entry.id"))
    cogs_je_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entry.id"))
    # Multi-currency: document is denominated in `currency_code`; `fx_rate` is
    # NGN per 1 unit captured at issue. NGN docs use NGN / 1.0 (the default),
    # so existing rows and reports are unaffected.
    currency_code: Mapped[str] = mapped_column(String(3), default="NGN")
    fx_rate: Mapped[float] = mapped_column(Float, default=1.0)

    customer = relationship("Customer")
    lines: Mapped[list["SalesInvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan",
        order_by="SalesInvoiceLine.id",
    )

    @property
    def subtotal(self) -> float:
        return msum(l.subtotal for l in self.lines)

    @property
    def tax_total(self) -> float:
        return msum(l.tax_amount for l in self.lines)

    @property
    def grand_total(self) -> float:
        return round(self.subtotal + self.tax_total, 2)

    @property
    def outstanding(self) -> float:
        return round(self.grand_total - self.amount_paid, 2)


class SalesInvoiceLine(Base):
    __tablename__ = "sales_invoice_line"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("sales_invoice.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("product.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)  # captured at invoice
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)

    invoice: Mapped[SalesInvoice] = relationship(back_populates="lines")
    product = relationship("Product")

    @property
    def subtotal(self) -> float:
        return round(self.qty * self.unit_price, 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)


class Receipt(Base):
    """Cash received from a customer, optionally against an invoice."""
    __tablename__ = "receipt"
    # Idempotency: a (customer, reference) pair is unique when a reference is
    # given. NULL references stay distinct (SQL NULL semantics), so reference-
    # less receipts are unaffected; a repeated reference (retry/replay) is
    # rejected at the DB as a backstop to the service-level guard.
    __table_args__ = (
        Index("ix_receipt_customer_reference", "customer_id", "reference",
              unique=True),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales_invoice.id"))
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_account.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # Amount applied to the invoice, in the invoice's currency (see
    # services.sales.record_receipt); equals `amount` for NGN. A void reverses
    # invoice.amount_paid by these same units, not the NGN cash figure.
    applied_amount: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(32), default="BANK")  # BANK | CASH | CARD
    reference: Mapped[Optional[str]] = mapped_column(String(64))
    je_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entry.id"))
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)

    customer = relationship("Customer")
    invoice = relationship("SalesInvoice")
    bank_account = relationship("BankAccount")


# ---- Purchase cycle ------------------------------------------------------


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)

    supplier = relationship("Supplier")
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.id",
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_line"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("product.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    product = relationship("Product")


class Bill(Base):
    __tablename__ = "bill"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), nullable=False)
    po_id: Mapped[Optional[int]] = mapped_column(ForeignKey("purchase_order.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0)
    je_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entry.id"))
    # Multi-currency: see SalesInvoice. NGN / 1.0 by default.
    currency_code: Mapped[str] = mapped_column(String(3), default="NGN")
    fx_rate: Mapped[float] = mapped_column(Float, default=1.0)

    supplier = relationship("Supplier")
    lines: Mapped[list["BillLine"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan",
        order_by="BillLine.id",
    )

    @property
    def subtotal(self) -> float:
        return msum(l.subtotal for l in self.lines)

    @property
    def tax_total(self) -> float:
        return msum(l.tax_amount for l in self.lines)

    @property
    def grand_total(self) -> float:
        return round(self.subtotal + self.tax_total, 2)

    @property
    def outstanding(self) -> float:
        return round(self.grand_total - self.amount_paid, 2)


class BillLine(Base):
    __tablename__ = "bill_line"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        ForeignKey("bill.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("product.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)
    # Optional override of the inventory/expense account this line posts to.
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"))

    bill: Mapped[Bill] = relationship(back_populates="lines")
    product = relationship("Product")
    account = relationship("Account")

    @property
    def subtotal(self) -> float:
        return round(self.qty * self.unit_cost, 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)


class Payment(Base):
    """Cash paid to a supplier, optionally against a bill."""
    __tablename__ = "payment"
    # Idempotency backstop, mirroring Receipt — see note there.
    __table_args__ = (
        Index("ix_payment_supplier_reference", "supplier_id", "reference",
              unique=True),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), nullable=False)
    bill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bill.id"))
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_account.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # Amount applied to the bill, in the bill's currency (see record_payment).
    applied_amount: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(32), default="BANK")
    reference: Mapped[Optional[str]] = mapped_column(String(64))
    je_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entry.id"))
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)

    supplier = relationship("Supplier")
    bill = relationship("Bill")
    bank_account = relationship("BankAccount")


# ---- Inventory movements -------------------------------------------------


class StockMovement(Base):
    """A single stock-in or stock-out event. Source links back to the document
    (invoice/bill/adjustment) that caused the movement."""
    __tablename__ = "stock_movement"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)
    warehouse_id: Mapped[Optional[int]] = mapped_column(ForeignKey("warehouse.id"))
    qty_in: Mapped[float] = mapped_column(Float, default=0.0)
    qty_out: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    avg_cost_after: Mapped[float] = mapped_column(Float, default=0.0)
    qty_on_hand_after: Mapped[float] = mapped_column(Float, default=0.0)
    source_kind: Mapped[Optional[str]] = mapped_column(String(32))  # BILL|INVOICE|ADJUSTMENT|OPENING
    source_id: Mapped[Optional[int]] = mapped_column(Integer)
    memo: Mapped[Optional[str]] = mapped_column(String(255))

    product = relationship("Product")
    warehouse = relationship("Warehouse")


# ---- Payroll ------------------------------------------------------------


class PayrollRun(Base):
    __tablename__ = "payroll_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)
    je_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entry.id"))

    payslips: Mapped[list["PayrollPayslip"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
    )


class PayrollPayslip(Base):
    __tablename__ = "payroll_payslip"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_run.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), nullable=False)
    gross: Mapped[float] = mapped_column(Float, default=0.0)
    paye: Mapped[float] = mapped_column(Float, default=0.0)
    pension_employee: Mapped[float] = mapped_column(Float, default=0.0)
    pension_employer: Mapped[float] = mapped_column(Float, default=0.0)
    other_deductions: Mapped[float] = mapped_column(Float, default=0.0)
    net_pay: Mapped[float] = mapped_column(Float, default=0.0)

    run: Mapped[PayrollRun] = relationship(back_populates="payslips")
    employee = relationship("Employee")
