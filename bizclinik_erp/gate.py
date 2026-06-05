"""Plan-based feature gating for Streamlit pages.

Call ``gate.require_feature("multi_currency", "Multi-currency")`` at the top of a
premium page (after auth.require_login). If the active tenant's plan doesn't
unlock it, the page shows an upgrade prompt and stops. Single-tenant / legacy
installs (no active tenant) are never gated.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

# Which plan first unlocks each gated feature (for the upgrade message).
_REQUIRES = {
    "bank_reconciliation": "Starter",
    "firs_einvoice": "Starter",
    "recurring": "Starter",
    "multi_currency": "Business",
    "crm": "Business",
    "budgets": "Business",
    "api": "Business",
}


def _active_tenant() -> Optional[str]:
    try:
        from . import auth
        return auth.active_tenant()
    except Exception:
        return None


def allows(feature: str) -> bool:
    from .services import billing
    return billing.allows(_active_tenant(), feature)


def require_feature(feature: str, label: Optional[str] = None) -> None:
    """Stop the page with an upgrade prompt if the plan doesn't unlock ``feature``."""
    if allows(feature):
        return
    from .services import billing
    plan = billing.effective_plan(_active_tenant())
    needed = _REQUIRES.get(feature, "a higher")
    label = label or feature.replace("_", " ").title()
    st.warning(
        f"🔒 **{label}** isn't included in your **{plan.name}** plan.\n\n"
        f"Upgrade to **{needed}** on the **Billing** page to unlock it.",
        icon="🔒",
    )
    st.stop()


def plan_badge() -> None:
    """Small sidebar caption showing the active plan."""
    from .services import billing
    p = billing.effective_plan(_active_tenant())
    st.sidebar.caption(f"Plan: **{p.name}**")
