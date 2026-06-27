"""Trakit365 ERP — application entry point.

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

st.set_page_config(page_title="Trakit365 ERP", layout="wide", page_icon="📊",
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


def _vertical() -> str:
    """The active tenant's industry vertical ('school' tailors the nav)."""
    try:
        from bizclinik_erp.db import get_session
        from bizclinik_erp.models import Company
        with get_session() as s:
            co = s.query(Company).first()
            return (co.vertical or "general") if co else "general"
    except Exception:
        return "general"


@st.cache_data(ttl=30, show_spinner=False)
def _pending_approvals(_tenant_key: str) -> int:
    try:
        from bizclinik_erp.db import get_session
        from bizclinik_erp.services import approvals as _appr
        with get_session() as s:
            return _appr.pending_count(s)
    except Exception:
        return 0


_n_pending = _pending_approvals(auth.active_tenant() or "default")
_appr_title = f"Approvals ({_n_pending})" if _n_pending else "Approvals"


# --------------------------------------------------------------------------- #
# Grouped navigation — tailored to the tenant's vertical                      #
# --------------------------------------------------------------------------- #
from bizclinik_erp.nav import build_nav_spec

try:
    _is_operator = auth.is_platform_admin()
except Exception:
    _is_operator = False

NAV = {}
for _group, _pages in build_nav_spec(_vertical(), _appr_title,
                                     platform_admin=_is_operator):
    NAV[_group] = [
        st.Page(p["path"], title=p["title"], icon=p["icon"],
                default=p["default"],
                **({"url_path": p["url_path"]} if p.get("url_path") else {}))
        for p in _pages
    ]

pg = st.navigation(NAV, position="sidebar")
# Render the sign-out globally (before the page body) so it is present on EVERY
# page — including pages that early-stop before their own bottom-of-page call,
# e.g. the company-setup screen the operator's empty tenant lands on. The
# per-page calls then no-op for this run (force=True resets the guard).
auth.render_logout_in_sidebar(force=True)
pg.run()
