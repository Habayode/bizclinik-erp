"""Billing — subscription plans and status for the active tenant."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui
from bizclinik_erp.services import billing, payments

st.set_page_config(page_title="Billing · Trakit365 ERP", layout="wide",
                    page_icon="💳")
ui.inject_brand()
auth.require_login()
# Operator-only: subscriptions/plans are managed centrally by the platform
# operator, not by individual tenants. (Nav-hiding is cosmetic; this is the gate.)
auth.require_platform_admin()
ui.hero("Billing", "Subscription plan & payment status", badge="$",
        right_label="Module", right_value="Subscriptions")

tenant = auth.active_tenant()
if not tenant:
    st.info("Billing applies to a registered business (tenant). Create or pick a "
            "business first on the Tenants page.")
    st.stop()

provider = payments.get_provider()
if not provider.configured():
    st.warning("No payment provider configured yet. Free plan works now; paid "
               "plans activate once a provider key (Paystack / Flutterwave / "
               "Moniepoint) is set on the server via PAYMENTS_PROVIDER.",
               icon="⚠️")
else:
    st.caption(f"Payment provider: **{provider.name}**")

# ---- current subscription ---------------------------------------------------
sub = billing.current_subscription(tenant)
st.subheader("Current subscription")
if sub:
    cols = st.columns(3)
    cols[0].metric("Plan", sub["plan_code"].title())
    cols[1].metric("Status", "Active" if sub["is_active"] else sub["status"].title())
    end = sub.get("current_period_end")
    cols[2].metric("Renews / ends", end.strftime("%Y-%m-%d") if end else "—")
else:
    st.info("No subscription yet — choose a plan below.")

# ---- what's unlocked right now ---------------------------------------------
_FEATURE_LABELS = {
    "bank_reconciliation": "Bank reconciliation",
    "firs_einvoice": "FIRS e-invoice drafts",
    "recurring": "Recurring transactions",
    "multi_currency": "Multi-currency",
    "crm": "CRM",
    "budgets": "Budgets",
    "api": "REST API + webhooks",
}
eff = billing.effective_plan(tenant)
ent = billing.entitlements(tenant)
st.subheader("What your plan unlocks")
ec1, ec2 = st.columns([2, 1])
with ec1:
    for code in sorted(billing.GATED_FEATURES):
        label = _FEATURE_LABELS.get(code, code)
        if code in ent["unlocks"]:
            st.markdown(f"✅ {label}")
        else:
            st.markdown(f"🔒 {label}")
with ec2:
    cap = ent["max_users"]
    st.metric("User accounts", "Unlimited" if cap is None else f"Up to {cap}")
    st.caption("Core accounting (sales, purchases, inventory, banking, payroll, "
               "tax, reports) is included on every plan.")

st.divider()
st.subheader("Plans")
cycle = st.radio(
    "Billing cycle", ["Monthly", "Annual — 2 months free"],
    horizontal=True, key="bill_cycle")
is_annual = cycle.startswith("Annual")
interval = "yearly" if is_annual else "monthly"

plans = billing.list_plans()
cols = st.columns(len(plans))
for col, p in zip(cols, plans):
    with col:
        current = "  ✓ current" if (sub and eff.code == p["code"]
                                    and sub["is_active"]) else ""
        st.markdown(f"### {p['name']}{current}")
        if p["is_free"]:
            st.markdown("**Free**")
        elif is_annual:
            yr = p["annual_price_ngn"]
            st.markdown(f"**₦{yr:,.0f}/yr**")
            st.caption(f"≈ ₦{yr / 12:,.0f}/mo · **2 months free** "
                       f"(vs ₦{p['price_ngn'] * 12:,.0f} monthly)")
        else:
            st.markdown(f"**₦{p['price_ngn']:,.0f}/mo**")
            st.caption(f"or ₦{p['annual_price_ngn']:,.0f}/yr (2 months free)")
        cap = p["max_users"]
        st.caption(f"👥 {'Unlimited users' if cap is None else f'Up to {cap} users'}")
        for f in p["features"]:
            st.markdown(f"- {f}")
        btn_label = ("Choose Free" if p["is_free"]
                     else f"Choose {p['name']} ({'Annual' if is_annual else 'Monthly'})")
        if st.button(btn_label, key=f"plan_{p['code']}",
                     use_container_width=True):
            try:
                res = billing.start_subscription(
                    tenant, p["code"], interval=interval,
                    email=(auth.current_user() or {}).get("username", "admin")
                    + "@" + tenant + ".local")
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
            else:
                if res.get("free"):
                    st.success("Activated the Free plan.")
                    st.rerun()
                elif res.get("authorization_url"):
                    amt = res.get("amount_ngn", 0)
                    st.success(f"Checkout created for ₦{amt:,.0f} "
                               f"({'annual' if is_annual else 'monthly'}) — "
                               "complete payment to activate:")
                    st.link_button("Pay now", res["authorization_url"],
                                   use_container_width=True)
                    st.caption(f"Reference: {res['reference']}")

auth.render_logout_in_sidebar()
