"""Billing — subscription plans and status for the active tenant."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui
from bizclinik_erp.services import billing, payments

st.set_page_config(page_title="Billing · BizClinik ERP", layout="wide",
                    page_icon="💳")
ui.inject_brand()
auth.require_login()
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

st.divider()
st.subheader("Plans")
plans = billing.list_plans()
cols = st.columns(len(plans))
for col, p in zip(cols, plans):
    with col:
        price = "Free" if p["is_free"] else f"₦{p['price_ngn']:,.0f}/{p['interval'][:2]}"
        st.markdown(f"### {p['name']}")
        st.markdown(f"**{price}**")
        for f in p["features"]:
            st.markdown(f"- {f}")
        if st.button(f"Choose {p['name']}", key=f"plan_{p['code']}",
                     use_container_width=True):
            try:
                res = billing.start_subscription(
                    tenant, p["code"],
                    email=(auth.current_user() or {}).get("username", "admin")
                    + "@" + tenant + ".local")
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
            else:
                if res.get("free"):
                    st.success("Activated the Free plan.")
                    st.rerun()
                elif res.get("authorization_url"):
                    st.success("Checkout created — complete payment to activate:")
                    st.link_button("Pay now", res["authorization_url"],
                                   use_container_width=True)
                    st.caption(f"Reference: {res['reference']}")

auth.render_logout_in_sidebar()
