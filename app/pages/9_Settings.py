"""Settings: company profile + master data lookups (customers, suppliers, banks)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (
    Account,
    BankAccount,
    Company,
    Customer,
    Supplier,
)
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Settings · BizClinik ERP", layout="wide",
                    page_icon="⚙️")
ui.inject_brand()
auth.require_login()
ui.hero("Settings", "Company profile · customers · suppliers · banks",
         badge="ST", right_label="Module", right_value="Master data")

tab_co, tab_cu, tab_su, tab_ba = st.tabs(
    ["🏢 Company", "👥 Customers", "🚚 Suppliers", "🏦 Bank accounts"]
)


with tab_co:
    with get_session() as s:
        company = s.query(Company).first()
    with st.form("company"):
        name = st.text_input("Name", value=company.name if company else "")
        rc = st.text_input("RC number", value=company.rc_number if company else "")
        addr = st.text_area("Address", value=company.address if company else "")
        email = st.text_input("Email", value=company.email if company else "")
        phone = st.text_input("Phone", value=company.phone if company else "")
        vat = st.text_input("VAT number", value=company.vat_number if company else "")
        submit = st.form_submit_button("Save", type="primary")
    if submit:
        with get_session() as s:
            c = s.query(Company).first()
            if not c:
                c = Company(name=name)
                s.add(c)
            c.name = name; c.rc_number = rc; c.address = addr
            c.email = email; c.phone = phone; c.vat_number = vat
        st.success("Saved.")


with tab_cu:
    with get_session() as s:
        rows = [{"id": c.id, "code": c.code, "name": c.name,
                  "email": c.email, "phone": c.phone, "address": c.address,
                  "active": c.is_active}
                 for c in s.execute(select(Customer).order_by(Customer.code)).scalars()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Add customer")
    with st.form("cust"):
        code = st.text_input("Code")
        name = st.text_input("Name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        addr = st.text_area("Address")
        submit = st.form_submit_button("Save", type="primary")
    if submit and code and name:
        with get_session() as s:
            s.add(Customer(code=code, name=name, email=email or None,
                            phone=phone or None, address=addr or None))
        st.success(f"Added {code}")


with tab_su:
    with get_session() as s:
        rows = [{"id": x.id, "code": x.code, "name": x.name,
                  "email": x.email, "phone": x.phone, "address": x.address,
                  "active": x.is_active}
                 for x in s.execute(select(Supplier).order_by(Supplier.code)).scalars()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Add supplier")
    with st.form("sup"):
        code = st.text_input("Code", key="sup_code")
        name = st.text_input("Name", key="sup_name")
        email = st.text_input("Email", key="sup_email")
        phone = st.text_input("Phone", key="sup_phone")
        addr = st.text_area("Address", key="sup_addr")
        submit = st.form_submit_button("Save", type="primary")
    if submit and code and name:
        with get_session() as s:
            s.add(Supplier(code=code, name=name, email=email or None,
                            phone=phone or None, address=addr or None))
        st.success(f"Added {code}")


with tab_ba:
    with get_session() as s:
        rows = [{"id": b.id, "code": b.code, "name": b.name,
                  "bank": b.bank, "account_no": b.account_number,
                  "gl_account": b.gl_account.code if b.gl_account else "",
                  "active": b.is_active}
                 for b in s.execute(select(BankAccount).order_by(BankAccount.code)).scalars()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Add bank account")
    with get_session() as s:
        asset_opts = {f"{a.code} — {a.name}": a.id
                       for a in s.execute(select(Account).where(
                          Account.code.like("11%"), Account.is_postable == True  # noqa: E712
                       ).order_by(Account.code)).scalars()}
    with st.form("ba"):
        code = st.text_input("Code", key="ba_code")
        name = st.text_input("Name", key="ba_name")
        bank = st.text_input("Bank", key="ba_bank")
        acct_no = st.text_input("Account number", key="ba_no")
        gl = st.selectbox("GL account", list(asset_opts.keys()))
        submit = st.form_submit_button("Save", type="primary")
    if submit and code and name and gl:
        with get_session() as s:
            s.add(BankAccount(code=code, name=name, bank=bank or None,
                                account_number=acct_no or None,
                                gl_account_id=asset_opts[gl]))
        st.success(f"Added {code}")

auth.render_logout_in_sidebar()
