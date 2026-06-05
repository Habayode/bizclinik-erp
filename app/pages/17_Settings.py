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

tab_co, tab_cu, tab_su, tab_ba, tab_tpl = st.tabs(
    ["🏢 Company", "👥 Customers", "🚚 Suppliers", "🏦 Bank accounts",
     "🎨 Invoice template"]
)


with tab_co:
    with get_session() as s:
        company = s.query(Company).first()
    with st.form("company"):
        name = st.text_input("Name", value=company.name if company else "")
        c1, c2 = st.columns(2)
        rc = c1.text_input("RC number", value=company.rc_number if company else "",
                            help="CAC registration number (Corporate Affairs Commission).")
        tin = c2.text_input("TIN", value=getattr(company, "tin", "") or "" if company else "",
                            help="Tax Identification Number (FIRS/JTB). Distinct from the RC number.")
        addr = st.text_area("Address", value=company.address if company else "")
        email = st.text_input("Email", value=company.email if company else "")
        phone = st.text_input("Phone", value=company.phone if company else "")
        c3, c4 = st.columns(2)
        vat = c3.text_input("VAT number", value=company.vat_number if company else "")
        service_id = c4.text_input(
            "FIRS Service ID",
            value=getattr(company, "firs_service_id", "") or "" if company else "",
            help="8-character ID assigned by FIRS at e-invoicing onboarding. "
                 "Used as the middle segment of the IRN. Leave blank until onboarded.")
        submit = st.form_submit_button("Save", type="primary")
    if submit:
        with get_session() as s:
            c = s.query(Company).first()
            if not c:
                c = Company(name=name)
                s.add(c)
            c.name = name; c.rc_number = rc; c.address = addr
            c.email = email; c.phone = phone; c.vat_number = vat
            c.tin = tin or None; c.firs_service_id = service_id or None
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


with tab_tpl:
    from bizclinik_erp.services import invoice_template as tpl_svc
    st.caption("Brand this tenant's invoice PDFs. Changes apply to every "
               "invoice generated from this business.")
    with get_session() as s:
        tpl = tpl_svc.get_or_create(s)
        cur_accent = tpl.accent_color or "#1F3864"
        cur_style = tpl.template_style or "classic"
        cur_pay = tpl.payment_instructions or ""
        cur_thanks = tpl.thank_you_note or ""
        cur_footer = tpl.footer_note or ""
        has_logo = tpl.logo is not None

    with st.form("invoice_template"):
        c1, c2 = st.columns(2)
        accent = c1.color_picker("Accent colour", value=cur_accent)
        style = c2.selectbox("Layout style", ["classic", "modern", "minimal"],
                             index=["classic", "modern", "minimal"].index(cur_style)
                             if cur_style in ("classic", "modern", "minimal") else 0)
        pay = st.text_area("Payment instructions",
                           value=cur_pay, placeholder="Bank: GTBank\nAccount: 0123456789")
        thanks = st.text_input("Thank-you note", value=cur_thanks,
                               placeholder="Thank you for your business!")
        footer = st.text_input("Footer note", value=cur_footer,
                               placeholder="Generated by BizClinik ERP")
        logo_file = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
        remove_logo = st.checkbox("Remove current logo") if has_logo else False
        if has_logo and not remove_logo:
            st.caption("✓ A logo is currently set.")
        saved = st.form_submit_button("Save template", type="primary")

    if saved:
        logo_bytes = logo_file.read() if logo_file is not None else None
        logo_mime = logo_file.type if logo_file is not None else None
        with get_session() as s:
            tpl_svc.update(s, accent_color=accent, template_style=style,
                           payment_instructions=pay, thank_you_note=thanks,
                           footer_note=footer, logo=logo_bytes, logo_mime=logo_mime,
                           clear_logo=bool(remove_logo))
        st.success("Invoice template saved.")


auth.render_logout_in_sidebar()
