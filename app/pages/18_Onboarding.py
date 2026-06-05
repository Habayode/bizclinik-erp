"""Onboarding wizard — guided first-run setup."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Account, BankAccount, Company
from bizclinik_erp.services import coa_templates
from bizclinik_erp.services.ledger import post_journal, JELine
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui


st.set_page_config(page_title="Onboarding · BizClinik ERP", layout="wide",
                    page_icon="🚀")
ui.inject_brand()
auth.require_login()
ui.hero("Onboarding", "Set up your business in a few steps",
         badge="ON", right_label="Module", right_value="Getting started")


steps = st.tabs([
    "1 · Company", "2 · Industry COA", "3 · Opening balances", "4 · Finish"
])


# ---- Step 1: Company ------------------------------------------------------

with steps[0]:
    st.subheader("Company profile")
    st.caption("This appears on every invoice, statement and report.")
    with get_session() as s:
        company = s.query(Company).first()
    with st.form("ob_company"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Business name", value=company.name if company else "")
        rc = c2.text_input("RC number", value=company.rc_number if company else "")
        addr = st.text_area("Address", value=company.address if company else "")
        c3, c4, c5 = st.columns(3)
        email = c3.text_input("Email", value=company.email if company else "")
        phone = c4.text_input("Phone", value=company.phone if company else "")
        vat = c5.text_input("VAT / TIN", value=company.vat_number if company else "")
        submit = st.form_submit_button("Save & continue", type="primary")
    if submit:
        with get_session() as s:
            c = s.query(Company).first()
            if not c:
                c = Company(name=name)
                s.add(c)
            c.name = name
            c.rc_number = rc
            c.address = addr
            c.email = email
            c.phone = phone
            c.vat_number = vat
        st.success("Company saved. Move to step 2 → Industry COA.")


# ---- Step 2: Industry COA -------------------------------------------------

with steps[1]:
    st.subheader("Pick your industry")
    st.caption("We'll add accounts that match how your business books costs. "
               "Your universal chart of accounts stays — this just layers on "
               "industry-relevant accounts. Safe to apply more than one.")
    tpls = coa_templates.list_templates()
    cols = st.columns(2)
    for i, t in enumerate(tpls):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{t['label']}**")
                st.caption(t["description"])
                st.caption(f"Adds {t['account_count']} accounts")
                if st.button(f"Apply {t['label']}", key=f"tpl_{t['key']}"):
                    with get_session() as s:
                        n = coa_templates.apply_template(s, t["key"])
                    st.success(f"Added {n} {t['label']} accounts.")


# ---- Step 3: Opening balances --------------------------------------------

with steps[2]:
    st.subheader("Opening balances")
    st.caption("Enter what your business owns and owes as at the start date. "
               "We post one balanced opening journal entry. Leave blank to skip.")
    with get_session() as s:
        postable = s.execute(
            select(Account).where(Account.is_postable == True)  # noqa: E712
            .order_by(Account.code)
        ).scalars().all()
        opts = {f"{a.code} — {a.name}": a.id for a in postable}

    as_of = st.date_input("Opening date", value=date(date.today().year, 1, 1))
    st.markdown("Enter each opening balance. Use the **debit** column for "
                "assets/expenses, **credit** for liabilities/equity/income. "
                "The entry must balance before it can post.")
    seed = pd.DataFrame([
        {"account": list(opts.keys())[0] if opts else "", "debit": 0.0, "credit": 0.0},
    ])
    grid = st.data_editor(
        seed, num_rows="dynamic", width="stretch",
        column_config={
            "account": st.column_config.SelectboxColumn(
                "Account", options=list(opts.keys()), required=True),
            "debit": st.column_config.NumberColumn("Debit (₦)", min_value=0.0, format="%.2f"),
            "credit": st.column_config.NumberColumn("Credit (₦)", min_value=0.0, format="%.2f"),
        },
        key="ob_grid",
    )
    tot_dr = float(grid["debit"].fillna(0).sum())
    tot_cr = float(grid["credit"].fillna(0).sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Total debit", ui.money(tot_dr))
    c2.metric("Total credit", ui.money(tot_cr))
    c3.metric("Balanced", "✅" if abs(tot_dr - tot_cr) < 0.01 and tot_dr > 0 else "❌")

    if st.button("Post opening balances", type="primary"):
        lines = []
        for _, row in grid.iterrows():
            aid = opts.get(row.get("account") or "")
            if not aid:
                continue
            dr = float(row.get("debit") or 0)
            cr = float(row.get("credit") or 0)
            if dr == 0 and cr == 0:
                continue
            lines.append(JELine(account_id=aid, debit=dr, credit=cr,
                                 memo="Opening balance"))
        if not lines:
            st.error("Nothing to post.")
        elif abs(tot_dr - tot_cr) > 0.01:
            st.error("Debits must equal credits before posting.")
        else:
            try:
                with get_session() as s:
                    je = post_journal(s, as_of, "Opening balances", lines,
                                      source_kind="OPENING",
                                      user_id=auth.current_user_id())
                st.success(f"Posted opening balances as {je.entry_no}.")
            except Exception as e:
                st.error(str(e))


# ---- Step 4: Finish -------------------------------------------------------

with steps[3]:
    st.subheader("You're set up")
    with get_session() as s:
        company = s.query(Company).first()
        n_accts = s.query(Account).count()
        n_banks = s.query(BankAccount).count()
    checks = [
        ("Company profile", bool(company and company.name), "Set your business name in step 1"),
        ("Chart of accounts", n_accts > 0, "Seeded automatically"),
        ("Bank accounts", n_banks > 0, "Add one in Settings → Bank accounts"),
    ]
    for label, ok, hint in checks:
        if ok:
            st.markdown(f"✅ **{label}**")
        else:
            st.markdown(f"⬜ **{label}** — {hint}")
    st.divider()
    st.markdown("**Next steps:**")
    st.markdown(
        "- Add customers & suppliers in **Settings**\n"
        "- Import a BizClinik workbook in **Data**\n"
        "- Issue your first invoice in **Sales**\n"
        "- Create staff logins in **Admin**"
    )


auth.render_logout_in_sidebar()
