"""Tenants — register isolated businesses (multi-tenant control plane).

Each tenant gets its own database; users, books and reports are fully
isolated. Until at least one tenant is created the app runs in single-tenant
mode against the default database.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp import tenancy
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui


st.set_page_config(page_title="Tenants · BizClinik ERP", layout="wide",
                    page_icon="🏬")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.users",
                   error="Admins only — sign in with an admin account.")
ui.hero("Tenants", "Register and isolate multiple businesses",
         badge="TN", right_label="Module", right_value="Multi-tenant")


st.info(
    "Each tenant is a completely separate set of books with its own users, "
    "chart of accounts and data. After you create the first tenant, everyone "
    "picks their business at login. The current single-tenant data stays as "
    "the default until you migrate it."
)

cur = auth.active_tenant()
if cur:
    st.caption(f"You are currently working in tenant: **{cur}**")

st.subheader("Registered tenants")
rows = [{"slug": t["slug"], "name": t["name"], "active": t["is_active"],
         "created": str(t.get("created_at") or "")[:19]}
        for t in tenancy.list_tenants(active_only=False)]
if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
else:
    st.caption("No tenants yet — single-tenant mode.")

st.divider()
st.subheader("Create a tenant")
with st.form("new_tenant"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Business name", placeholder="Acme Trading Ltd")
    slug = c2.text_input("Slug (URL-safe id)", placeholder="acme-trading",
                          help="lowercase letters, digits, hyphens")
    admin_pw = st.text_input("Initial admin password for this tenant",
                              type="password")
    submit = st.form_submit_button("Create tenant", type="primary")
if submit:
    if not (name and slug and admin_pw):
        st.error("Name, slug and admin password are all required.")
    else:
        try:
            t = tenancy.create_tenant(slug, name, admin_password=admin_pw)
            st.success(
                f"Created tenant **{t['name']}** ({t['slug']}). Its admin login "
                f"is username `admin` with the password you set. Sign out and "
                f"pick this business at the login screen to enter it."
            )
        except ValueError as e:
            st.error(str(e))


auth.render_logout_in_sidebar()
