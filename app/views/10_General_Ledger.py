"""General Ledger: Chart of Accounts, Trial Balance, manual journal entry, account inquiry."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Account, AccountType, JournalEntry
from bizclinik_erp.services.ledger import (
    JELine,
    general_ledger,
    post_journal,
    trial_balance,
)
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="General Ledger · Trakit365 ERP", layout="wide",
                    page_icon="📒")
ui.inject_brand()
auth.require_login()
auth.require_perm("post.journal")
ui.hero("General Ledger", "Trial balance · journal entries · account inquiry",
         badge="GL", right_label="Module", right_value="Bookkeeping", compact=True)

tab_tb, tab_coa, tab_open, tab_je, tab_inq, tab_journals = st.tabs(
    ["⚖️ Trial Balance", "📚 Chart of Accounts", "🏁 Opening balances",
     "➕ New journal", "🔍 Account inquiry", "📋 Journals"]
)


with tab_tb:
    as_of = st.date_input("As of", value=date.today())
    with get_session() as s:
        rows = trial_balance(s, as_of=as_of)
    if rows:
        df = pd.DataFrame(rows)
        tot_dr = df["debit"].sum()
        tot_cr = df["credit"].sum()
        ui.dataframe(df, hide_index=True, width="stretch")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total DR", f"₦{tot_dr:,.2f}")
        c2.metric("Total CR", f"₦{tot_cr:,.2f}")
        c3.metric("Balanced?", "✅" if abs(tot_dr - tot_cr) < 0.01 else "❌")
    else:
        st.info("No postings yet.")


with tab_coa:
    with get_session() as s:
        accts = s.execute(select(Account).order_by(Account.code)).scalars().all()
        rows = [{"code": a.code, "name": a.name, "type": a.type.value,
                  "postable": a.is_postable, "active": a.is_active} for a in accts]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    ui.bulk_import_expander("account", "Accounts")
    st.divider()
    st.subheader("Add account")
    with st.form("acct"):
        code = st.text_input("Code")
        name = st.text_input("Name")
        type_ = st.selectbox("Type", [t.value for t in AccountType])
        with get_session() as s:
            parents = {f"{a.code} — {a.name}": a.id
                        for a in s.execute(select(Account).order_by(Account.code)).scalars()}
        parent = st.selectbox("Parent (optional)", [""] + list(parents.keys()))
        postable = st.checkbox("Postable", value=True)
        submit = st.form_submit_button("Save", type="primary")
    if submit:
        with get_session() as s:
            s.add(Account(code=code, name=name, type=AccountType(type_),
                           parent_id=parents.get(parent) if parent else None,
                           is_postable=postable))
        st.success(f"Added {code}")


with tab_open:
    from bizclinik_erp.services import opening_balance as ob
    st.subheader("Opening balances")
    st.caption("Going live with an existing business? Upload your closing "
               "**trial balance** and Trakit365 posts it as one balanced "
               "opening journal — so your books start with real figures.")
    with get_session() as s:
        already = ob.existing_opening(s)
        plug_opts = {f"{a.code} — {a.name}": a.code for a in s.execute(
            select(Account).where(Account.type == AccountType.EQUITY,
                                  Account.is_postable == True)  # noqa: E712
            .order_by(Account.code)).scalars()}
    if already is not None:
        st.info(f"✓ Opening balances already posted as **{already.entry_no}**. "
                "Void that journal (Journals tab → void) to re-import.")
    else:
        oc1, oc2 = st.columns(2)
        as_of = oc1.date_input("Balances as at", value=date.today(),
                               help="Usually the day before you start using the app.")
        plug_default = next((i for i, c in enumerate(plug_opts.values())
                             if c == ob.DEFAULT_PLUG_CODE), 0)
        plug_label = oc2.selectbox(
            "Balancing account (if totals don't tie)",
            list(plug_opts.keys()) or ["—"], index=plug_default,
            help="A small debit/credit difference is posted here — usually "
                 "Retained Earnings / Opening Balance Equity.")
        st.download_button("⬇ Download trial-balance template (.xlsx)",
                           data=ob.template_bytes(),
                           file_name="Trakit365_opening_balances_template.xlsx",
                           mime="application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet", key="ob_tpl")
        up = st.file_uploader("Upload your filled trial balance", type=["xlsx"],
                              key="ob_upload")
        if up is not None:
            try:
                df = pd.read_excel(up)
            except Exception as e:   # noqa: BLE001
                st.error(f"Couldn't read that file: {e}")
                df = None
            if df is not None:
                st.caption("Preview:")
                ui.dataframe(df.head(30), hide_index=True, width="stretch")
                if st.button("Post opening balances", type="primary",
                             key="ob_post"):
                    try:
                        with get_session() as s:
                            res = ob.import_trial_balance(
                                s, df, as_of=as_of,
                                plug_account_code=plug_opts.get(plug_label),
                                user_id=auth.current_user_id())
                        msg = (f"Opening balances posted as {res['je_no']} — "
                               f"DR ₦{res['total_debit']:,.2f} = CR "
                               f"₦{res['total_credit']:,.2f}.")
                        if res["balancing_amount"]:
                            msg += (f" Balanced ₦{res['balancing_amount']:,.2f} "
                                    f"to {res['balancing_account']}.")
                        ui.flash(msg); st.rerun()
                    except ValueError as e:
                        st.error(str(e))


with tab_je:
    st.subheader("New journal entry")
    with get_session() as s:
        opts = {f"{a.code} — {a.name}": a.id
                 for a in s.execute(select(Account).where(
                    Account.is_postable == True).order_by(Account.code)).scalars()}  # noqa: E712
    if opts:
        with st.form("je"):
            edate = st.date_input("Date", value=date.today())
            memo = st.text_input("Memo")
            seed = pd.DataFrame([
                {"account": list(opts.keys())[0], "debit": 0.0, "credit": 0.0,
                 "line_memo": ""},
                {"account": list(opts.keys())[0], "debit": 0.0, "credit": 0.0,
                 "line_memo": ""},
            ])
            grid = st.data_editor(
                seed, num_rows="dynamic",
                column_config={
                    "account": st.column_config.SelectboxColumn(
                        "Account", options=list(opts.keys()), required=True),
                    "debit": st.column_config.NumberColumn("Debit", min_value=0.0),
                    "credit": st.column_config.NumberColumn("Credit", min_value=0.0),
                    "line_memo": st.column_config.TextColumn("Line memo"),
                },
            )
            submit = st.form_submit_button("Post", type="primary")
        if submit:
            lines = []
            for _, row in grid.iterrows():
                a = opts.get(row.get("account") or "")
                if not a:
                    continue
                dr = float(row.get("debit") or 0)
                cr = float(row.get("credit") or 0)
                if dr == 0 and cr == 0:
                    continue
                lines.append(JELine(account_id=a, debit=dr, credit=cr,
                                     memo=row.get("line_memo") or None))
            if not lines:
                st.error("No lines.")
            else:
                try:
                    with get_session() as s:
                        je = post_journal(s, edate, memo or "Journal", lines)
                    st.success(f"Posted {je.entry_no} — DR {je.total_debit} = CR {je.total_credit}")
                except ValueError as e:
                    st.error(str(e))


with tab_inq:
    with get_session() as s:
        opts = {f"{a.code} — {a.name}": a.id
                 for a in s.execute(select(Account).where(
                    Account.is_postable == True).order_by(Account.code)).scalars()}  # noqa: E712
    if opts:
        sel = st.selectbox("Account", list(opts.keys()))
        c1, c2 = st.columns(2)
        ps = c1.date_input("Period start", value=date(date.today().year, 1, 1))
        pe = c2.date_input("Period end", value=date.today())
        with get_session() as s:
            rows = general_ledger(s, opts[sel], period_start=ps, period_end=pe)
        if rows:
            ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.caption("No activity in period.")


with tab_journals:
    with get_session() as s:
        jes = s.execute(select(JournalEntry).order_by(
            JournalEntry.entry_date.desc(), JournalEntry.id.desc()).limit(200)).scalars().all()
        rows = [{
            "entry_no": j.entry_no, "date": j.entry_date,
            "memo": j.memo, "source": f"{j.source_kind or ''} #{j.source_id or ''}",
            "DR": j.total_debit, "CR": j.total_credit,
            "balanced": "✅" if j.is_balanced else "❌",
        } for j in jes]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

auth.render_logout_in_sidebar()
