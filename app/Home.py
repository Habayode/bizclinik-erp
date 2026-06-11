"""BizClinik ERP — application entry point.

Defines the grouped sidebar navigation (Finance & Accounting · CRM · HR ·
System) via st.navigation and runs the selected module page.

Run with:  python -m streamlit run app/Home.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from bizclinik_erp.observability import init_sentry
    init_sentry("streamlit")
except Exception:
    pass

import streamlit as st

from bizclinik_erp.db import init_db
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="BizClinik ERP", layout="wide", page_icon="📊",
                    initial_sidebar_state="expanded")

# Module pages each call st.set_page_config at the top (so they also work when
# run standalone). Under st.navigation the entry already set it, so make the
# per-page calls no-ops to avoid "set_page_config can only be called once".
st.set_page_config = lambda *a, **k: None  # type: ignore[assignment]

init_db()
ui.inject_brand()
auth.require_login()

# Show the active tenant's subscription plan in the sidebar.
try:
    from bizclinik_erp import gate as _gate
    if auth.active_tenant():
        _gate.plan_badge()
except Exception:
    pass


def _page(path: str, title: str, icon: str, default: bool = False):
    return st.Page(path, title=title, icon=icon, default=default)


# --------------------------------------------------------------------------- #
# Grouped navigation                                                          #
# --------------------------------------------------------------------------- #
NAV = {
    "Overview": [
        _page("pages/0_Dashboard.py", "Dashboard", "📊", default=True),
    ],
    "Finance & Accounting": [
        _page("pages/1_Sales.py", "Sales", "🧾"),
        _page("pages/2_Purchases.py", "Purchases", "📥"),
        _page("pages/3_Inventory.py", "Inventory", "📦"),
        _page("pages/4_Banking.py", "Banking", "🏦"),
        _page("pages/7_Bank_Reconciliation.py", "Bank Reconciliation", "🔗"),
        _page("pages/6_Fixed_Assets.py", "Fixed Assets", "🏭"),
        _page("pages/8_Recurring.py", "Recurring", "🔁"),
        _page("pages/9_FIRS_Einvoice.py", "FIRS E-Invoice", "🧾"),
        _page("pages/20_Currencies.py", "Currencies", "💱"),
        _page("pages/10_General_Ledger.py", "General Ledger", "📚"),
        _page("pages/13_Budgets.py", "Budgets", "🎯"),
        _page("pages/11_Month_End.py", "Month-End", "📅"),
        _page("pages/12_Statements.py", "Statements", "📃"),
        _page("pages/15_Reports.py", "Reports", "📈"),
        _page("pages/28_Approvals.py", "Approvals", "✅"),
    ],
    "CRM": [
        _page("pages/23_CRM.py", "CRM", "🤝"),
    ],
    "HR": [
        _page("pages/24_Employees.py", "Employees", "🧑‍💼"),
        _page("pages/25_Recruitment.py", "Recruitment", "🧲"),
        _page("pages/26_Leave.py", "Leave", "🌴"),
        _page("pages/5_Payroll.py", "Payroll", "💷"),
    ],
    "System": [
        _page("pages/18_Onboarding.py", "Onboarding", "🚀"),
        _page("pages/17_Settings.py", "Settings", "⚙️"),
        _page("pages/19_Admin.py", "Admin", "🛡️"),
        _page("pages/14_Notifications.py", "Notifications", "🔔"),
        _page("pages/16_Data.py", "Data", "🗄️"),
        _page("pages/21_Tenants.py", "Tenants", "🏢"),
        _page("pages/22_Billing.py", "Billing", "💳"),
        _page("pages/27_User_Manual.py", "User Manual", "📖"),
    ],
}

pg = st.navigation(NAV, position="sidebar")
pg.run()

# Floating help assistant (bottom-right) on every page, with a live data
# snapshot (cached 60s per business) so it can answer data questions too.
@st.cache_data(ttl=60, show_spinner=False)
def _assistant_snapshot(_tenant_key: str) -> dict:
    from bizclinik_erp.db import get_session
    from bizclinik_erp import assistant as _a
    try:
        with get_session() as s:
            return _a.compute_snapshot(s)
    except Exception:
        return {}


try:
    from bizclinik_erp import assistant
    _snap = _assistant_snapshot(auth.active_tenant() or "default")
    assistant.render_floating_widget(_snap)
except Exception:
    pass
