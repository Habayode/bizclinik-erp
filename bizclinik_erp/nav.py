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


DASHBOARD = _p("views/0_Dashboard.py", "Dashboard", "📊", default=True)

_HR_PAGES = [
    _p("views/24_Employees.py", "Employees", "🧑‍💼"),
    _p("views/25_Recruitment.py", "Recruitment", "🧲"),
    _p("views/26_Leave.py", "Leave", "🌴"),
    _p("views/5_Payroll.py", "Payroll", "💷"),
]

# Operator-only System pages. The Tenants console manages EVERY business on the
# platform; Billing/subscriptions are managed centrally by the operator; Data
# exposes the server DB path + a destructive wipe — none of these belong to an
# ordinary tenant. They are shown only to the platform operator (see
# auth.is_platform_admin) — never to a tenant admin. Hiding them here is
# cosmetic; the real gate is auth.require_platform_admin() at the top of each page.
_TENANTS_PATH = "views/21_Tenants.py"
_BILLING_PATH = "views/22_Billing.py"
_DATA_PATH = "views/16_Data.py"
_OPERATOR_ONLY = {_TENANTS_PATH, _BILLING_PATH, _DATA_PATH}

_SYSTEM_PAGES = [
    _p("views/18_Onboarding.py", "Onboarding", "🚀"),
    _p("views/17_Settings.py", "Settings", "⚙️"),
    _p("views/19_Admin.py", "Admin", "🛡️"),
    _p("views/14_Notifications.py", "Notifications", "🔔"),
    _p("views/16_Data.py", "Data", "🗄️"),
    _p(_TENANTS_PATH, "Tenants", "🏢"),
    _p(_BILLING_PATH, "Billing", "💳"),
    _p("views/27_User_Manual.py", "User Manual", "📖"),
]


def _system_pages(platform_admin: bool) -> list:
    """System group, minus the operator-only pages (Tenants, Billing) for
    non-operators."""
    return [p for p in _SYSTEM_PAGES
            if platform_admin or p["path"] not in _OPERATOR_ONLY]


def build_nav_spec(vertical: str = "general",
                   appr_title: str = "Approvals", *,
                   platform_admin: bool = False) -> list[tuple]:
    approvals = _p("views/28_Approvals.py", appr_title, "✅",
                   url_path="approvals-queue")
    # Shared finance pages, in display order.
    sales = _p("views/1_Sales.py", "Sales", "🧾")
    purchases = _p("views/2_Purchases.py", "Purchases", "📥")
    inventory = _p("views/3_Inventory.py", "Inventory", "📦")
    banking = _p("views/4_Banking.py", "Banking", "🏦")
    bankrec = _p("views/7_Bank_Reconciliation.py", "Bank Reconciliation", "🔗")
    assets = _p("views/6_Fixed_Assets.py", "Fixed Assets", "🏭")
    recurring = _p("views/8_Recurring.py", "Recurring", "🔁")
    firs = _p("views/9_FIRS_Einvoice.py", "FIRS E-Invoice", "🧾")
    currencies = _p("views/20_Currencies.py", "Currencies", "💱")
    gl = _p("views/10_General_Ledger.py", "General Ledger", "📚")
    budgets = _p("views/13_Budgets.py", "Budgets", "🎯")
    monthend = _p("views/11_Month_End.py", "Month-End", "📅")
    statements = _p("views/12_Statements.py", "Statements", "📃")
    reports = _p("views/15_Reports.py", "Reports", "📈")
    agents = _p("views/38_Agents.py", "AI Agents", "🤖")

    if vertical == "school":
        # School-first: a School Dashboard is the landing, the School group is
        # up top, the accounting modules sit under "Bursary", and the
        # school-irrelevant modules (CRM, FIRS e-invoice, multi-currency) are
        # hidden. The generic financial dashboard stays as "Finance Dashboard".
        school_group = [
            _p("views/29_School_Dashboard.py", "School Dashboard", "📊", default=True),
            _p("views/30_School_Setup.py", "School Setup", "🏫"),
            _p("views/32_School_Students.py", "Students", "🎓"),
            _p("views/33_School_Fees.py", "School Fees", "💰"),
            _p("views/34_School_Attendance.py", "Attendance", "🗓"),
            _p("views/35_School_Results.py", "Results", "📝"),
            _p("views/36_School_Teachers.py", "Teachers", "👩‍🏫"),
            _p("views/37_School_Notifications.py", "Parent Notifications", "📣"),
        ]
        finance_dash = _p("views/0_Dashboard.py", "Finance Dashboard", "📊")
        return [
            ("School", school_group),
            ("Bursary", [
                finance_dash, sales, purchases, inventory, banking, bankrec,
                assets, recurring, gl, budgets, monthend, statements, reports,
                approvals]),
            ("Intelligence", [agents]),
            ("HR", list(_HR_PAGES)),
            ("System", _system_pages(platform_admin)),
        ]

    # General accounting ERP (the School group is not shown).
    return [
        ("Overview", [DASHBOARD]),
        ("Finance & Accounting", [
            sales, purchases, inventory, banking, bankrec, assets, recurring,
            firs, currencies, gl, budgets, monthend, statements, reports, approvals]),
        ("Intelligence", [agents]),
        ("CRM", [_p("views/23_CRM.py", "CRM", "🤝")]),
        ("HR", list(_HR_PAGES)),
        ("System", _system_pages(platform_admin)),
    ]
