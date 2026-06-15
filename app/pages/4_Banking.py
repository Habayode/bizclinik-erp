"""Banking: balances, transfers, charges, reconciliation."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Account, BankAccount
from bizclinik_erp.services import banking as bank_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Banking · Trakit365 ERP", layout="wide",
                    page_icon="🏦")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.banks")
ui.hero("Banking", "Balances · transfers · charges · reconciliation",
         badge="BK", right_label="Module", right_value="Cash management")

tab_bal, tab_xfer, tab_chg, tab_rec = st.tabs(
    ["💼 Balances", "↔️ Transfer", "📉 Charge", "✅ Reconcile"]
)


def _bank_options(session) -> dict[str, int]:
    return {f"{b.code} — {b.name}": b.id
            for b in session.execute(select(BankAccount).order_by(BankAccount.code)).scalars()}


with tab_bal:
    with get_session() as s:
        banks = s.execute(select(BankAccount).order_by(BankAccount.code)).scalars().all()
        rows = []
        for b in banks:
            rows.append({
                "code": b.code, "name": b.name,
                "bank": b.bank, "account_no": b.account_number,
                "gl_balance": bank_svc.bank_balance(s, b.id),
                "active": b.is_active,
            })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Add bank account")
    with get_session() as s:
        asset_opts = {f"{a.code} — {a.name}": a.id
                       for a in s.execute(select(Account).where(
                          Account.code.like("11%"), Account.is_postable == True  # noqa: E712
                       ).order_by(Account.code)).scalars()}
    if not asset_opts:
        st.info("Initialise the chart of accounts first (Data → Reset and seed).")
    else:
        with st.form("new_bank"):
            code = st.text_input("Code", key="ba_code",
                                  help="Short unique code (e.g. BANK2, CASH-LAG)")
            name = st.text_input("Name", key="ba_name")
            bank = st.text_input("Bank", key="ba_bank")
            acct_no = st.text_input("Account number", key="ba_no")
            opening = st.number_input("Opening balance (₦)", min_value=0.0,
                                       format="%.2f", value=0.0, key="ba_open")
            gl = st.selectbox("GL account", list(asset_opts.keys()),
                               help="Asset account that this bank posts to")
            submit = st.form_submit_button("Add bank account", type="primary")
        if submit:
            if not code or not name:
                st.error("Code and name are required.")
            else:
                with get_session() as s:
                    s.add(BankAccount(
                        code=code.strip(), name=name.strip(),
                        bank=bank or None, account_number=acct_no or None,
                        opening_balance=opening,
                        gl_account_id=asset_opts[gl],
                    ))
                st.success(f"Added {code}")


with tab_xfer:
    with get_session() as s:
        opts = _bank_options(s)
    if len(opts) >= 2:
        with st.form("xfer"):
            keys = list(opts.keys())
            src = st.selectbox("From", keys, key="xfer_from")
            dst = st.selectbox("To", [k for k in keys if k != src], key="xfer_to")
            amt = st.number_input("Amount (₦)", min_value=0.0, format="%.2f")
            on = st.date_input("Date", value=date.today())
            memo = st.text_input("Memo", value="Bank transfer")
            submit = st.form_submit_button("Post transfer", type="primary")
        if submit and amt > 0:
            with get_session() as s:
                je = bank_svc.post_bank_transfer(
                    s, from_bank_id=opts[src], to_bank_id=opts[dst],
                    on=on, amount=amt, memo=memo,
                )
                st.success(f"Transfer posted as {je.entry_no}")
    else:
        st.info("Need at least 2 bank accounts to transfer.")


with tab_chg:
    with get_session() as s:
        opts = _bank_options(s)
    if opts:
        with st.form("chg"):
            sel = st.selectbox("Bank", list(opts.keys()), key="chg_sel")
            amt = st.number_input("Charge (₦)", min_value=0.0, format="%.2f", key="chg_amt")
            on = st.date_input("Date", value=date.today(), key="chg_on")
            memo = st.text_input("Memo", value="Bank charge", key="chg_memo")
            submit = st.form_submit_button("Post charge", type="primary")
        if submit and amt > 0:
            with get_session() as s:
                je = bank_svc.post_bank_charge(s, bank_account_id=opts[sel],
                                                 on=on, amount=amt, memo=memo)
                st.success(f"Charge posted as {je.entry_no}")


with tab_rec:
    with get_session() as s:
        opts = _bank_options(s)
    if opts:
        sel = st.selectbox("Bank", list(opts.keys()), key="rec_sel")
        stmt_bal = st.number_input("Statement balance (₦)", format="%.2f")
        as_of = st.date_input("As-of", value=date.today())
        if st.button("Compare"):
            with get_session() as s:
                r = bank_svc.reconcile(s, opts[sel],
                                        statement_balance=stmt_bal, as_of=as_of)
            c1, c2, c3 = st.columns(3)
            c1.metric("GL balance", f"₦{r['gl_balance']:,.2f}")
            c2.metric("Statement", f"₦{r['statement_balance']:,.2f}")
            c3.metric("Diff", f"₦{r['difference']:,.2f}",
                       delta_color="off" if r["reconciled"] else "inverse")
            if r["reconciled"]:
                st.success("Reconciled ✅")
            else:
                st.warning("Difference — investigate unreconciled items.")

auth.render_logout_in_sidebar()
