"""Tenants — register isolated businesses (multi-tenant control plane).

Each tenant gets its own database; users, books and reports are fully
isolated. Until at least one tenant is created the app runs in single-tenant
mode against the default database.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp import tenancy
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui


# Canonical per-tenant login URL. One level under the apex
# (acme-erp.hagai.online) so it's covered by the free *.hagai.online TLS cert;
# the app auto-selects the tenant from the host. Override the template when you
# move to a dedicated domain (e.g. "https://{slug}.bizclinik.app").
_TENANT_URL_TEMPLATE = os.environ.get(
    "BIZCLINIK_TENANT_URL_TEMPLATE", "https://{slug}-erp.hagai.online")


def _login_url(slug: str) -> str:
    return _TENANT_URL_TEMPLATE.format(slug=slug)


st.set_page_config(page_title="Tenants · Trakit365 ERP", layout="wide",
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
rows = [{"slug": t["slug"], "name": t["name"], "login url": _login_url(t["slug"]),
         "active": t["is_active"], "created": str(t.get("created_at") or "")[:19]}
        for t in tenancy.list_tenants(active_only=False)]
if rows:
    st.dataframe(
        pd.DataFrame(rows), hide_index=True, width="stretch",
        column_config={"login url": st.column_config.LinkColumn("login url")},
    )
    st.caption(
        "Each business signs in at its own **login url** — the link auto-selects "
        "that tenant (no business picker). Wiring a new tenant's subdomain on the "
        "server is one command: `deploy/linux/add-tenant-subdomain.sh <slug>`."
    )
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
                f"Created tenant **{t['name']}** ({t['slug']}). Admin login is "
                f"username `admin` with the password you set."
            )
            st.markdown(f"**Login URL:** {_login_url(t['slug'])}")
            st.caption(
                "To activate that subdomain on the server, run "
                f"`deploy/linux/add-tenant-subdomain.sh {t['slug']}` once. "
                "Until then, sign in via the business picker at the main URL."
            )
        except ValueError as e:
            st.error(str(e))


st.divider()
st.subheader("REST API keys")
st.caption("A key scoped to a tenant lets external systems read/write only that "
            "tenant's books via https://api.hagai.online. The key is shown once.")

key_rows = [{"id": k["id"], "tenant": k["tenant_slug"] or "(default DB)",
             "label": k["label"], "active": k["is_active"],
             "created": k["created_at"], "last_used": k["last_used_at"]}
            for k in tenancy.list_api_keys()]
if key_rows:
    st.dataframe(pd.DataFrame(key_rows), hide_index=True, width="stretch")

with st.form("new_key"):
    tenants_for_key = ["(default DB)"] + [t["slug"] for t in tenancy.list_tenants()]
    c1, c2 = st.columns(2)
    key_tenant = c1.selectbox("Scope (tenant)", tenants_for_key)
    key_label = c2.text_input("Label", placeholder="e.g. POS integration")
    submit_key = st.form_submit_button("Generate API key", type="primary")
if submit_key:
    slug_arg = None if key_tenant == "(default DB)" else key_tenant
    try:
        plaintext = tenancy.create_api_key(slug_arg, key_label or "")
        st.success("API key created — copy it now, it won't be shown again:")
        st.code(plaintext, language="text")
        st.caption(f"Use header  X-API-Key: {plaintext[:12]}…  against "
                   f"https://api.hagai.online")
    except ValueError as e:
        st.error(str(e))

if key_rows:
    with st.expander("Revoke a key"):
        rid = st.number_input("Key id to revoke", min_value=1, step=1)
        if st.button("Revoke", type="secondary"):
            tenancy.revoke_api_key(int(rid))
            st.warning(f"Revoked key #{int(rid)}")


auth.render_logout_in_sidebar()
