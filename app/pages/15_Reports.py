"""Reports: P&L, Balance Sheet, Cash Flow, AR/AP Aging, VAT return."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp.services import reports
from bizclinik_erp.services.tax import vat_return, wht_position
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Reports · Trakit365 ERP", layout="wide",
                    page_icon="📈")
ui.inject_brand()
auth.require_login()
ui.hero("Reports", "Profit & Loss · Balance Sheet · Cash Flow · Aging · Tax",
         badge="RP", right_label="Module", right_value="Financial reports")


def money(x: float) -> str:
    return ui.money(x)


tab_pnl, tab_bs, tab_cf, tab_ar, tab_ap, tab_vat = st.tabs(
    ["📊 Profit & Loss", "⚖️ Balance Sheet", "💧 Cash Flow",
     "→ AR Aging", "← AP Aging", "🧾 VAT & WHT"]
)


with tab_pnl:
    c1, c2 = st.columns(2)
    ps = c1.date_input("Period start", value=date(date.today().year, 1, 1), key="pnl_ps")
    pe = c2.date_input("Period end", value=date.today(), key="pnl_pe")
    with get_session() as s:
        r = reports.profit_and_loss(s, period_start=ps, period_end=pe)

    def show(title, lines, total):
        st.markdown(f"**{title}** — {money(total)}")
        if lines:
            st.dataframe(pd.DataFrame(lines), hide_index=True, width="stretch")
        else:
            st.caption("(no entries)")

    show("Revenue", r["revenue"], r["total_revenue"])
    show("Less: Direct costs", r["direct_costs"], r["total_direct_costs"])
    st.markdown(f"### Gross profit: {money(r['gross_profit'])}")
    show("Less: Operating expenses", r["operating_expenses"], r["total_operating_expenses"])
    st.markdown(f"### Operating profit: {money(r['operating_profit'])}")
    show("Plus: Other income", r["other_income"], r["total_other_income"])
    st.markdown(f"## Net profit: {money(r['net_profit'])}")


with tab_bs:
    as_of = st.date_input("As of", value=date.today(), key="bs_asof")
    with get_session() as s:
        r = reports.balance_sheet(s, as_of=as_of)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total assets", money(r["total_assets"]))
    c2.metric("Total liabilities", money(r["total_liabilities"]))
    c3.metric("Total equity", money(r["total_equity"]))
    c4.metric("Balanced", "✅" if r["balanced"] else "❌")

    a_col, le_col = st.columns(2)
    with a_col:
        st.markdown("#### Assets")
        if r["assets"]:
            st.dataframe(pd.DataFrame(r["assets"]), hide_index=True, width="stretch")
    with le_col:
        st.markdown("#### Liabilities")
        if r["liabilities"]:
            st.dataframe(pd.DataFrame(r["liabilities"]), hide_index=True, width="stretch")
        st.markdown("#### Equity")
        if r["equity"]:
            st.dataframe(pd.DataFrame(r["equity"]), hide_index=True, width="stretch")


with tab_cf:
    c1, c2 = st.columns(2)
    ps = c1.date_input("Period start", value=date(date.today().year, 1, 1), key="cf_ps")
    pe = c2.date_input("Period end", value=date.today(), key="cf_pe")
    with get_session() as s:
        cf = reports.cash_flow(s, period_start=ps, period_end=pe)

    for section in ("operating_activities", "investing_activities", "financing_activities"):
        st.markdown(f"### {section.replace('_', ' ').title()}")
        d = cf[section]
        df = pd.DataFrame([{"item": k, "amount": v} for k, v in d.items() if k != "total"])
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption(f"Subtotal: {money(d['total'])}")
    st.markdown(f"## Net change in cash: {money(cf['net_change_in_cash'])}")


with tab_ar:
    as_of = st.date_input("As of", value=date.today(), key="ar_asof")
    with get_session() as s:
        rows = reports.ar_aging(s, as_of=as_of)
    if rows:
        df = pd.DataFrame(rows).drop(columns=["customer_id"])
        st.dataframe(df, hide_index=True, width="stretch")
        st.metric("Total outstanding AR", money(df["total"].sum()))
    else:
        st.success("Nothing outstanding.")


with tab_ap:
    as_of = st.date_input("As of", value=date.today(), key="ap_asof")
    with get_session() as s:
        rows = reports.ap_aging(s, as_of=as_of)
    if rows:
        df = pd.DataFrame(rows).drop(columns=["supplier_id"])
        st.dataframe(df, hide_index=True, width="stretch")
        st.metric("Total outstanding AP", money(df["total"].sum()))
    else:
        st.success("Nothing outstanding.")


with tab_vat:
    c1, c2 = st.columns(2)
    ps = c1.date_input("Period start", value=date(date.today().year, 1, 1), key="vat_ps")
    pe = c2.date_input("Period end", value=date.today(), key="vat_pe")
    with get_session() as s:
        vr = vat_return(s, period_start=ps, period_end=pe)
        wht = wht_position(s, period_start=ps, period_end=pe)
    st.subheader("VAT return")
    a, b, c = st.columns(3)
    a.metric("Output VAT", money(vr["output_vat"]))
    b.metric("Input VAT", money(vr["input_vat"]))
    c.metric("Net payable", money(vr["net_payable"]))

    st.subheader("Withholding tax")
    a, b = st.columns(2)
    a.metric("WHT receivable (suffered)", money(wht["wht_suffered_receivable"]))
    b.metric("WHT payable (withheld)", money(wht["wht_withheld_payable"]))

auth.render_logout_in_sidebar()
