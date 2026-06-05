"""Currencies + exchange rates."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select, desc

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Currency, ExchangeRate
from bizclinik_erp.services import fx as fx_svc
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui


st.set_page_config(page_title="Currencies · BizClinik ERP", layout="wide",
                    page_icon="💱")
ui.inject_brand()
auth.require_login()
ui.hero("Currencies", "Foreign currencies + exchange rates (NGN functional)",
         badge="CU", right_label="Module", right_value="Multi-currency")


tab_cur, tab_rates = st.tabs(["💱 Currencies", "📈 Exchange rates"])


with tab_cur:
    st.subheader("Currencies")
    st.caption("NGN is the base / functional currency — the ledger is always "
               "in NGN. Foreign-denominated invoices and bills convert to NGN "
               "at the rate captured when they're posted.")
    with get_session() as s:
        rows = [{"code": c.code, "name": c.name, "symbol": c.symbol,
                  "base": c.is_base, "active": c.is_active}
                 for c in s.execute(select(Currency).order_by(Currency.code)).scalars()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Add currency")
    with st.form("add_cur"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("ISO code (3 letters)", max_chars=3)
        name = c2.text_input("Name")
        symbol = c3.text_input("Symbol", max_chars=8)
        submit = st.form_submit_button("Add", type="primary")
    if submit and code and name:
        with get_session() as s:
            cc = code.strip().upper()
            if s.get(Currency, cc):
                st.warning(f"{cc} already exists.")
            else:
                s.add(Currency(code=cc, name=name.strip(), symbol=symbol.strip()))
                st.success(f"Added {cc}")


with tab_rates:
    st.subheader("Exchange rates")
    st.caption("Rate = NGN per 1 unit of the foreign currency.")
    with get_session() as s:
        rate_rows = [{
            "currency": r.currency_code, "date": r.rate_date,
            "rate (NGN per 1)": r.rate, "source": r.source or "",
        } for r in s.execute(
            select(ExchangeRate).order_by(desc(ExchangeRate.rate_date),
                                           ExchangeRate.currency_code).limit(200)
        ).scalars()]
    if rate_rows:
        st.dataframe(pd.DataFrame(rate_rows), hide_index=True, width="stretch")
    else:
        st.info("No rates yet. Add one below before issuing foreign-currency documents.")

    st.divider()
    st.subheader("Set a rate")
    with get_session() as s:
        foreign = [c.code for c in s.execute(
            select(Currency).where(Currency.is_base == False,  # noqa: E712
                                    Currency.is_active == True)  # noqa: E712
            .order_by(Currency.code)).scalars()]
    if not foreign:
        st.info("Add a foreign currency first.")
    else:
        with st.form("set_rate"):
            c1, c2, c3 = st.columns(3)
            cur = c1.selectbox("Currency", foreign)
            rdate = c2.date_input("Rate date", value=date.today())
            rate = c3.number_input("Rate (NGN per 1)", min_value=0.0,
                                    format="%.4f", value=0.0)
            src = st.text_input("Source (e.g. CBN, parallel)")
            submit = st.form_submit_button("Save rate", type="primary")
        if submit and rate > 0:
            with get_session() as s:
                fx_svc.set_rate(s, cur, rdate, rate, source=src or None,
                                 user_id=auth.current_user_id())
                st.success(f"Set {cur} = ₦{rate:,.4f} on {rdate}")


st.divider()
st.subheader("Unrealized FX revaluation")
st.caption("Marks open foreign-currency invoices & bills to the rate as of a "
           "date. Report only — review with your accountant before booking a "
           "period-end revaluation entry.")
rev_date = st.date_input("Revalue as of", value=date.today(), key="fx_reval_date")
if st.button("Run revaluation", type="primary"):
    with get_session() as s:
        rep = fx_svc.unrealized_fx_revaluation(s, as_of=rev_date)
    net = rep["net_unrealized"]
    st.metric("Net unrealized FX (P&L impact)", f"₦{net:,.2f}",
              delta=("gain" if net > 0 else "loss" if net < 0 else "flat"))
    rows = rep["receivables"] + rep["payables"]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No open foreign-currency receivables or payables to revalue.")
    if rep["skipped"]:
        st.warning("Skipped (no rate on file): "
                   + ", ".join(x["ref"] for x in rep["skipped"]))


auth.render_logout_in_sidebar()
