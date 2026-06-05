"""Month-End Close: adjusting entries (accruals, prepaids, deferred revenue)
and a computed close checklist with a one-click period-close button."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Account
from bizclinik_erp.services import closing as closing_svc
from bizclinik_erp.services import fiscal as fiscal_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Month-End Close · BizClinik ERP", layout="wide",
                    page_icon="📆")
ui.inject_brand()
auth.require_login()
ui.hero("Month-End Close", "Adjusting entries + close checklist", badge="MC",
         right_label="Module", right_value="Period close")


_PILL = {"ok": "ok", "pending": "warn", "na": "neutral"}
_LABEL = {"ok": "Done", "pending": "Pending", "na": "N/A"}


def _expense_accounts(session) -> dict[str, int]:
    from bizclinik_erp.models import AccountType
    accts = session.execute(
        select(Account).where(
            Account.type == AccountType.EXPENSE,
            Account.is_postable == True,  # noqa: E712
            Account.is_active == True,  # noqa: E712
        ).order_by(Account.code)
    ).scalars().all()
    return {f"{a.code} — {a.name}": a.id for a in accts}


tab_check, tab_accr, tab_prep, tab_defrev = st.tabs(
    ["✅ Checklist", "📥 Accruals", "📤 Prepaids", "🧾 Deferred revenue"]
)


with tab_check:
    c1, c2 = st.columns(2)
    year = c1.number_input("Year", min_value=2000, max_value=2100,
                            value=date.today().year, step=1)
    month = c2.number_input("Month", min_value=1, max_value=12,
                            value=date.today().month, step=1)
    year, month = int(year), int(month)

    with get_session() as s:
        checklist = closing_svc.close_checklist(s, year=year, month=month)

    for item in checklist:
        kind = _PILL.get(item["status"], "neutral")
        pill = ui.pill(_LABEL.get(item["status"], item["status"]), kind)
        st.markdown(
            ui._h(
                "<div style='display:flex; align-items:center; "
                "justify-content:space-between; padding:8px 0; "
                "border-bottom:1px solid #E5E7EB;'>"
                f"<div><b>{item['task']}</b><br>"
                f"<span style='font-size:0.8rem; color:#64748B;'>{item['detail']}</span></div>"
                f"<div>{pill}</div></div>"
            ),
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button("Close this period", type="primary", width="stretch"):
        try:
            with get_session() as s:
                fiscal_svc.close_period(s, year, month,
                                        user_id=auth.current_user_id())
            st.success(f"Closed period {year}-{month:02d}.")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not close period: {e}")


with tab_accr:
    st.subheader("Accrue an expense")
    st.caption("DR expense / CR Accrued Expenses (2160).")
    with get_session() as s:
        opts = _expense_accounts(s)
    if not opts:
        st.info("No postable expense accounts found.")
    else:
        with st.form("accrual"):
            on = st.date_input("Date", value=date.today(), key="accr_date")
            amount = st.number_input("Amount", min_value=0.0, step=1000.0,
                                     key="accr_amt")
            acct = st.selectbox("Expense account", list(opts.keys()),
                                key="accr_acct")
            memo = st.text_input("Memo", value="Month-end accrual",
                                 key="accr_memo")
            submit = st.form_submit_button("Post accrual", type="primary")
        if submit:
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                try:
                    with get_session() as s:
                        je = closing_svc.accrue_expense(
                            s, on=on, amount=float(amount),
                            expense_account_id=opts[acct], memo=memo)
                    st.success(f"Posted {je.entry_no} — {ui.money(float(amount))} accrued.")
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))


with tab_prep:
    st.subheader("Amortise a prepaid")
    st.caption("DR expense / CR Prepaid Expenses (1170).")
    with get_session() as s:
        opts = _expense_accounts(s)
    if not opts:
        st.info("No postable expense accounts found.")
    else:
        with st.form("prepaid"):
            on = st.date_input("Date", value=date.today(), key="prep_date")
            amount = st.number_input("Amount", min_value=0.0, step=1000.0,
                                     key="prep_amt")
            acct = st.selectbox("Expense account", list(opts.keys()),
                                key="prep_acct")
            memo = st.text_input("Memo", value="Prepaid amortisation",
                                 key="prep_memo")
            submit = st.form_submit_button("Post amortisation", type="primary")
        if submit:
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                try:
                    with get_session() as s:
                        je = closing_svc.amortize_prepaid(
                            s, on=on, amount=float(amount),
                            expense_account_id=opts[acct], memo=memo)
                    st.success(f"Posted {je.entry_no} — {ui.money(float(amount))} amortised.")
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))


with tab_defrev:
    st.subheader("Defer revenue")
    st.caption("DR Sales (4100) / CR Deferred Revenue (2170, or 2160 if absent).")
    with st.form("defrev"):
        on = st.date_input("Date", value=date.today(), key="def_date")
        amount = st.number_input("Amount", min_value=0.0, step=1000.0,
                                 key="def_amt")
        memo = st.text_input("Memo", value="Revenue deferral", key="def_memo")
        submit = st.form_submit_button("Post deferral", type="primary")
    if submit:
        if amount <= 0:
            st.error("Amount must be greater than zero.")
        else:
            try:
                with get_session() as s:
                    je = closing_svc.defer_revenue(
                        s, on=on, amount=float(amount), memo=memo)
                st.success(f"Posted {je.entry_no} — {ui.money(float(amount))} deferred.")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))


auth.render_logout_in_sidebar()
