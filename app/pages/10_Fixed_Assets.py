"""Fixed Assets: register, monthly depreciation, disposal."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import or_, select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (
    Account,
    AssetStatus,
    BankAccount,
    FixedAsset,
    JournalEntry,
    JournalLine,
)
from bizclinik_erp.services import assets as assets_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Fixed Assets · BizClinik ERP", layout="wide",
                    page_icon="🏭")
ui.inject_brand()
auth.require_login()
ui.hero("Fixed Assets", "Register · depreciation · disposal",
         badge="FA", right_label="Module", right_value="Asset accounting")


CATEGORY_OPTIONS = ["Equipment", "Furniture", "Vehicles", "Other"]


def _load_accounts(session, *, code_like: str | None = None, code_eq: str | None = None):
    q = select(Account).where(Account.is_active.is_(True), Account.is_postable.is_(True))
    if code_eq:
        q = q.where(Account.code == code_eq)
    elif code_like:
        q = q.where(Account.code.like(code_like))
    return session.execute(q.order_by(Account.code)).scalars().all()


tab_reg, tab_add, tab_run, tab_disp, tab_hist = st.tabs(
    ["📋 Register", "➕ Add asset", "🔄 Run depreciation",
     "💰 Dispose asset", "📜 Asset JE history"]
)


# ---- Register --------------------------------------------------------------
with tab_reg:
    as_of_reg = st.date_input("As of", value=date.today(), key="reg_as_of")
    with get_session() as s:
        rows = assets_svc.asset_register(s, as_of=as_of_reg)
    if rows:
        df = pd.DataFrame(rows)
        active = df[df["status"] == AssetStatus.ACTIVE.value]
        total_cost = float(active["cost"].sum()) if not active.empty else 0.0
        total_nbv = float(active["nbv"].sum()) if not active.empty else 0.0
        c1, c2, c3 = st.columns(3)
        c1.metric("Active assets", len(active))
        c2.metric("Total cost", f"₦{total_cost:,.2f}")
        c3.metric("Total NBV", f"₦{total_nbv:,.2f}")
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.info("No fixed assets registered yet.")


# ---- Add asset -------------------------------------------------------------
with tab_add:
    with get_session() as s:
        asset_accts = _load_accounts(s, code_like="12%")
        accum_accts = _load_accounts(s, code_eq="1290")
        dep_exp_accts = _load_accounts(s, code_eq="6600")
        asset_opts = {f"{a.code} — {a.name}": a.id for a in asset_accts}
        accum_opts = {f"{a.code} — {a.name}": a.id for a in accum_accts}
        dep_opts = {f"{a.code} — {a.name}": a.id for a in dep_exp_accts}

    if not (asset_opts and accum_opts and dep_opts):
        st.warning("Missing GL accounts. Make sure the chart of accounts is seeded.")
    else:
        with st.form("new_asset"):
            code = st.text_input("Code (unique)")
            name = st.text_input("Name")
            category = st.selectbox("Category", CATEGORY_OPTIONS)
            acquired = st.date_input("Acquired date", value=date.today())
            cost = st.number_input("Cost (₦)", min_value=0.0, format="%.2f")
            life = st.number_input("Useful life (months)",
                                    min_value=1, value=36, step=1)
            salvage = st.number_input("Salvage value (₦)", min_value=0.0,
                                       format="%.2f", value=0.0)
            asset_acct = st.selectbox("Asset GL account", list(asset_opts.keys()))
            accum_acct = st.selectbox("Accumulated depreciation account",
                                       list(accum_opts.keys()))
            dep_acct = st.selectbox("Depreciation expense account",
                                     list(dep_opts.keys()))
            submit = st.form_submit_button("Add asset", type="primary")
        if submit:
            if not code or not name:
                st.error("Code and name are required.")
            elif cost <= 0:
                st.error("Cost must be positive.")
            else:
                try:
                    with get_session() as s:
                        a = assets_svc.add_asset(
                            s,
                            code=code.strip(), name=name.strip(),
                            category=category,
                            acquired_date=acquired,
                            cost=cost, useful_life_months=int(life),
                            salvage_value=salvage,
                            gl_asset_account_id=asset_opts[asset_acct],
                            gl_accum_dep_account_id=accum_opts[accum_acct],
                            gl_dep_expense_account_id=dep_opts[dep_acct],
                        )
                    st.success(f"Added asset {a.code} — monthly depreciation "
                                f"₦{assets_svc.monthly_depreciation_amount(a):,.2f}")
                except Exception as e:
                    st.error(f"Failed: {e}")


# ---- Run depreciation ------------------------------------------------------
with tab_run:
    as_of_dep = st.date_input("Run depreciation through end of month preceding",
                                value=date.today(), key="dep_as_of")
    st.caption("Posts one JE per asset per month for every full month "
                "between each asset's last depreciation and the as-of date.")
    if st.button("Run depreciation", type="primary"):
        try:
            with get_session() as s:
                created = assets_svc.run_depreciation(s, as_of=as_of_dep)
            if created:
                st.success(f"Posted {len(created)} depreciation JE(s).")
            else:
                st.info("Nothing to post — all assets are up to date.")
        except Exception as e:
            st.error(f"Failed: {e}")


# ---- Dispose asset ---------------------------------------------------------
with tab_disp:
    with get_session() as s:
        active_assets = s.execute(
            select(FixedAsset).where(FixedAsset.status == AssetStatus.ACTIVE)
            .order_by(FixedAsset.code)
        ).scalars().all()
        a_opts = {f"{a.code} — {a.name} (NBV ₦{(a.cost - a.accumulated_depreciation):,.2f})": a.id
                   for a in active_assets}
        banks = s.execute(
            select(BankAccount).where(BankAccount.is_active.is_(True))
            .order_by(BankAccount.code)
        ).scalars().all()
        b_opts = {f"{b.code} — {b.name}": b.id for b in banks}

    if not a_opts:
        st.info("No active assets to dispose.")
    elif not b_opts:
        st.warning("Add a bank account first.")
    else:
        with st.form("dispose_asset"):
            sel = st.selectbox("Asset", list(a_opts.keys()))
            on = st.date_input("Disposal date", value=date.today(), key="disp_on")
            proceeds = st.number_input("Proceeds (₦)", min_value=0.0, format="%.2f")
            bank_sel = st.selectbox("Bank account", list(b_opts.keys()))
            submit = st.form_submit_button("Dispose", type="primary")
        if submit:
            try:
                with get_session() as s:
                    je = assets_svc.dispose_asset(
                        s, a_opts[sel],
                        on=on, proceeds=proceeds,
                        bank_account_id=b_opts[bank_sel],
                    )
                st.success(f"Asset disposed. JE {je.entry_no} posted "
                            f"(DR ₦{je.total_debit:,.2f} / CR ₦{je.total_credit:,.2f}).")
            except Exception as e:
                st.error(f"Failed: {e}")


# ---- Asset JE history ------------------------------------------------------
with tab_hist:
    with get_session() as s:
        all_assets = s.execute(
            select(FixedAsset).order_by(FixedAsset.code)
        ).scalars().all()
        h_opts = {f"{a.code} — {a.name}": a.id for a in all_assets}

    if not h_opts:
        st.info("No assets yet.")
    else:
        sel = st.selectbox("Asset", list(h_opts.keys()), key="hist_sel")
        asset_id = h_opts[sel]
        with get_session() as s:
            entries = s.execute(
                select(JournalEntry)
                .where(
                    or_(
                        JournalEntry.source_kind == "DEPRECIATION",
                        JournalEntry.source_kind == "ASSET_DISPOSAL",
                    ),
                    JournalEntry.source_id == asset_id,
                )
                .order_by(JournalEntry.entry_date, JournalEntry.id)
            ).scalars().all()
            rows = []
            for je in entries:
                for line in je.lines:
                    acct = s.get(Account, line.account_id)
                    rows.append({
                        "date": je.entry_date,
                        "entry_no": je.entry_no,
                        "source": je.source_kind,
                        "account": f"{acct.code} {acct.name}" if acct else "?",
                        "debit": line.debit,
                        "credit": line.credit,
                        "memo": line.memo or je.memo,
                    })
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.caption("No depreciation or disposal JEs yet for this asset.")


auth.render_logout_in_sidebar()
