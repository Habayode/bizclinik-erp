"""Tenant-aware sidebar navigation spec.

Pure data (no Streamlit) so it is unit-testable. `build_nav_spec(vertical)`
returns an ordered list of (group_title, [page-spec, ...]). A "school" tenant
gets a school-first, curated layout (School group up top, school-irrelevant
modules hidden); a "general" tenant gets the standard accounting layout and
does not see the School group at all.
"""
from __future__ import annotations

from typing import Optional


def _p(path: str, title: str, icon: str, *, default: bool = False,
       url_path: Optional[str] = None) -> dict:
    return {"path": path, "title": title, "icon": icon,
            "default": default, "url_path": url_path}


DASHBOARD = _p("pages/0_Dashboard.py", "Dashboard", "📊", default=True)

_HR_PAGES = [
    _p("pages/24_Employees.py", "Employees", "🧑‍💼"),
    _p("pages/25_Recruitment.py", "Recruitment", "🧲"),
    _p("pages/26_Leave.py", "Leave", "🌴"),
    _p("pages/5_Payroll.py", "Payroll", "💷"),
]

# Operator-only System pages. The Tenants console manages EVERY business on the
# platform; Billing/subscriptions are managed centrally by the operator, not by
# individual tenants. Both are shown only to the platform operator (see
# auth.is_platform_admin) — never to an ordinary tenant admin. Hiding them here
# is cosmetic; the real gate is auth.require_platform_admin() at the top of each
# page.
_TENANTS_PATH = "pages/21_Tenants.py"
_BILLING_PATH = "pages/22_Billing.py"
_OPERATOR_ONLY = {_TENANTS_PATH, _BILLING_PATH}

_SYSTEM_PAGES = [
    _p("pages/18_Onboarding.py", "Onboarding", "🚀"),
    _p("pages/17_Settings.py", "Settings", "⚙️"),
    _p("pages/19_Admin.py", "Admin", "🛡️"),
    _p("pages/14_Notifications.py", "Notifications", "🔔"),
    _p("pages/16_Data.py", "Data", "🗄️"),
    _p(_TENANTS_PATH, "Tenants", "🏢"),
    _p(_BILLING_PATH, "Billing", "💳"),
    _p("pages/27_User_Manual.py", "User Manual", "📖"),
]


def _system_pages(platform_admin: bool) -> list:
    """System group, minus the operator-only pages (Tenants, Billing) for
    non-operators."""
    return [p for p in _SYSTEM_PAGES
            if platform_admin or p["path"] not in _OPERATOR_ONLY]


def build_nav_spec(vertical: str = "general",
                   appr_title: str = "Approvals", *,
                   platform_admin: bool = False) -> list[tuple]:
    approvals = _p("pages/28_Approvals.py", appr_title, "✅",
                   url_path="approvals-queue")
    # Shared finance pages, in display order.
    sales = _p("pages/1_Sales.py", "Sales", "🧾")
    purchases = _p("pages/2_Purchases.py", "Purchases", "📥")
    inventory = _p("pages/3_Inventory.py", "Inventory", "📦")
    banking = _p("pages/4_Banking.py", "Banking", "🏦")
    bankrec = _p("pages/7_Bank_Reconciliation.py", "Bank Reconciliation", "🔗")
    assets = _p("pages/6_Fixed_Assets.py", "Fixed Assets", "🏭")
    recurring = _p("pages/8_Recurring.py", "Recurring", "🔁")
    firs = _p("pages/9_FIRS_Einvoice.py", "FIRS E-Invoice", "🧾")
    currencies = _p("pages/20_Currencies.py", "Currencies", "💱")
    gl = _p("pages/10_General_Ledger.py", "General Ledger", "📚")
    budgets = _p("pages/13_Budgets.py", "Budgets", "🎯")
    monthend = _p("pages/11_Month_End.py", "Month-End", "📅")
    statements = _p("pages/12_Statements.py", "Statements", "📃")
    reports = _p("pages/15_Reports.py", "Reports", "📈")

    if vertical == "school":
        # School-first: a School Dashboard is the landing, the School group is
        # up top, the accounting modules sit under "Bursary", and the
        # school-irrelevant modules (CRM, FIRS e-invoice, multi-currency) are
        # hidden. The generic financial dashboard stays as "Finance Dashboard".
        school_group = [
            _p("pages/29_School_Dashboard.py", "School Dashboard", "📊", default=True),
            _p("pages/30_School_Setup.py", "School Setup", "🏫"),
            _p("pages/32_School_Students.py", "Students", "🎓"),
            _p("pages/33_School_Fees.py", "School Fees", "💰"),
            _p("pages/34_School_Attendance.py", "Attendance", "🗓"),
            _p("pages/35_School_Results.py", "Results", "📝"),
            _p("pages/36_School_Teachers.py", "Teachers", "👩‍🏫"),
            _p("pages/37_School_Notifications.py", "Parent Notifications", "📣"),
        ]
        finance_dash = _p("pages/0_Dashboard.py", "Finance Dashboard", "📊")
        return [
            ("School", school_group),
            ("Bursary", [
                finance_dash, sales, purchases, inventory, banking, bankrec,
                assets, recurring, gl, budgets, monthend, statements, reports,
                approvals]),
            ("HR", list(_HR_PAGES)),
            ("System", _system_pages(platform_admin)),
        ]

    # General accounting ERP (the School group is not shown).
    return [
        ("Overview", [DASHBOARD]),
        ("Finance & Accounting", [
            sales, purchases, inventory, banking, bankrec, assets, recurring,
            firs, currencies, gl, budgets, monthend, statements, reports, approvals]),
        ("CRM", [_p("pages/23_CRM.py", "CRM", "🤝")]),
        ("HR", list(_HR_PAGES)),
        ("System", _system_pages(platform_admin)),
    ]
