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
    DocCounter,
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
from .crm import (
    Activity,
    ActivityKind,
    Deal,
    DealStage,
    Lead,
    LeadStatus,
)
from .hr import (
    ApplicationStage,
    Candidate,
    JobApplication,
    JobOpening,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    OpeningStatus,
)
from .approvals import ApprovalLimit, ApprovalRequest, ApprovalStatus
from .school import (
    AcademicSession,
    FeeType,
    SchoolClass,
    StudentFeeSchedule,
    Term,
)
from .school_enrol import (
    Student,
    StudentEnrolment,
    StudentStatus,
)
from .school_fees import (
    StudentFeeBilling,
)
from .school_ops import (
    Attendance,
    AttendanceStatus,
    StudentResult,
)
from .school_staff import (
    StaffType,
    TeacherProfile,
)

__all__ = [
    # master
    "AccountType", "Account", "BankAccount", "Company", "Customer",
    "Employee", "Product", "Supplier", "TaxCode", "Warehouse",
    # txn
    "DocCounter", "DocStatus", "JournalEntry", "JournalLine",
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
    # CRM
    "Lead", "LeadStatus", "Deal", "DealStage", "Activity", "ActivityKind",
    # HR — recruitment + leave
    "JobOpening", "OpeningStatus", "Candidate", "JobApplication",
    "ApplicationStage", "LeaveRequest", "LeaveType", "LeaveStatus",
    # Approvals
    "ApprovalLimit", "ApprovalRequest", "ApprovalStatus",
    # School (Phase 0 scaffolding)
    "AcademicSession", "Term", "SchoolClass", "FeeType", "StudentFeeSchedule",
    # School (Phase 1 — students + enrolment)
    "Student", "StudentEnrolment", "StudentStatus",
    # School (Phase 2 — fee billing)
    "StudentFeeBilling",
    # School (Phase 4 — attendance + results, GL-free)
    "Attendance", "AttendanceStatus", "StudentResult",
    # School (Phase 5 — teaching staff profiles, GL-free)
    "StaffType", "TeacherProfile",
]
