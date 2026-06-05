"""ORM model registry. Import order matters: master before txn so foreign
keys resolve when the metadata is collected."""

from .master import (
    Account,
    AccountType,
    BankAccount,
    Company,
    Customer,
    Employee,
    Product,
    Supplier,
    TaxCode,
    Warehouse,
)
from .assets import AssetStatus, DepreciationMethod, FixedAsset
from .audit import AuditAction, AuditLog
from .fiscal import FiscalPeriod, PeriodStatus
from .recon import BankStatement, BankStatementLine, StatementStatus
from .recurring import RecurringFrequency, RecurringKind, RecurringTemplate
from .users import Role, User, UserSession
from .einvoice import EInvoiceSubmission, EInvoiceStatus
from .txn import (
    Bill,
    BillLine,
    DocStatus,
    JournalEntry,
    JournalLine,
    Payment,
    PayrollPayslip,
    PayrollRun,
    PurchaseOrder,
    PurchaseOrderLine,
    Quotation,
    QuotationLine,
    Receipt,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    StockMovement,
)
from .budget import Budget, BudgetLine
from .fx import Currency, ExchangeRate
from .template import InvoiceTemplate

__all__ = [
    # master
    "AccountType", "Account", "BankAccount", "Company", "Customer",
    "Employee", "Product", "Supplier", "TaxCode", "Warehouse",
    # txn
    "DocStatus", "JournalEntry", "JournalLine",
    "Quotation", "QuotationLine", "SalesOrder", "SalesOrderLine",
    "SalesInvoice", "SalesInvoiceLine", "Receipt",
    "PurchaseOrder", "PurchaseOrderLine", "Bill", "BillLine", "Payment",
    "StockMovement", "PayrollRun", "PayrollPayslip",
    # fixed assets
    "FixedAsset", "DepreciationMethod", "AssetStatus",
    # reconciliation
    "BankStatement", "BankStatementLine", "StatementStatus",
    # recurring transactions
    "RecurringTemplate", "RecurringKind", "RecurringFrequency",
    # users + roles
    "User", "UserSession", "Role",
    # fiscal periods
    "FiscalPeriod", "PeriodStatus",
    # audit
    "AuditLog", "AuditAction",
    # FIRS e-invoice
    "EInvoiceSubmission", "EInvoiceStatus",
    # budgets
    "Budget", "BudgetLine",
    # multi-currency
    "Currency", "ExchangeRate",
    # per-tenant invoice branding
    "InvoiceTemplate",
]
