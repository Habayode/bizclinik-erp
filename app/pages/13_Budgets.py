"""Budgets: plan monthly amounts per account and compare against actuals."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Account, AccountType, Budget
from bizclinik_erp.services import budget as budget_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Budgets · BizClinik ERP", layout="wide",
                   page_icon="📐")
ui.inject_brand()
auth.require_login()
ui.hero("Budgets", "Plan vs actual by account", badge="BG",
        right_label="Module", right_value="Planning")


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _load_budgets() -> list[dict]:
    with get_session() as s:
        rows = s.execute(select(Budget).order_by(Budget.year.desc(), Budget.name)).scalars().all()
        return [{"id": b.id, "name": b.name, "year": b.year,
                 "is_active": b.is_active} for b in rows]


def _postable_pl_accounts() -> list[dict]:
    """Postable income + expense accounts, ordered by code."""
    with get_session() as s:
        accts = s.execute(
            select(Account).where(
                Account.type.in_([AccountType.INCOME, AccountType.EXPENSE]),
                Account.is_postable == True,  # noqa: E712
                Account.is_active == True,  # noqa: E712
            ).order_by(Account.code)
        ).scalars().all()
        return [{"id": a.id, "code": a.code, "name": a.name,
                 "type": a.type.value} for a in accts]


tab_list, tab_edit, tab_va = st.tabs(
    ["📋 Budgets", "✏️ Edit budget", "📊 Budget vs Actual"]
)


# ---- Budgets list ----------------------------------------------------------


with tab_list:
    ui.section("All budgets", "Annual plans on file")
    budgets = _load_budgets()
    if budgets:
        st.dataframe(pd.DataFrame(budgets), hide_index=True, width="stretch")
    else:
        st.caption("No budgets yet — create one below.")

    ui.section("Create budget", "")
    with st.form("create_budget_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", placeholder="e.g. FY2026 Operating Budget")
        year = c2.number_input("Year", min_value=2000, max_value=2100,
                               value=date.today().year, step=1)
        submit = st.form_submit_button("Create budget", type="primary")
    if submit:
        if not name.strip():
            st.error("Name is required.")
        else:
            with get_session() as s:
                budget_svc.create_budget(s, name=name.strip(), year=int(year))
            st.success(f"Created budget '{name.strip()}' for {int(year)}.")
            st.rerun()


# ---- Edit budget -----------------------------------------------------------


with tab_edit:
    budgets = _load_budgets()
    if not budgets:
        st.info("Create a budget first.")
    else:
        labels = {f"{b['name']} ({b['year']})": b["id"] for b in budgets}
        pick = st.selectbox("Budget", list(labels.keys()), key="edit_pick")
        budget_id = labels[pick]

        accounts = _postable_pl_accounts()
        if not accounts:
            st.warning("No postable income/expense accounts found.")
        else:
            # Build a grid: one row per account, columns Jan..Dec.
            with get_session() as s:
                existing = budget_svc.budget_summary(s, budget_id)  # touch summary
                from bizclinik_erp.models import BudgetLine
                lines = s.execute(
                    select(BudgetLine).where(BudgetLine.budget_id == budget_id)
                ).scalars().all()
                amt = {(ln.account_id, ln.month): ln.amount for ln in lines}

            grid_rows = []
            for a in accounts:
                row = {"Account": f"{a['code']} {a['name']}", "_account_id": a["id"]}
                for i, m in enumerate(_MONTHS, start=1):
                    row[m] = float(amt.get((a["id"], i), 0.0))
                grid_rows.append(row)
            grid_df = pd.DataFrame(grid_rows)

            ui.section("Monthly budget", "Enter planned amounts per account")
            edited = st.data_editor(
                grid_df,
                hide_index=True,
                width="stretch",
                disabled=["Account", "_account_id"],
                column_config={
                    "_account_id": None,
                    **{m: st.column_config.NumberColumn(m, format="%.2f", min_value=0.0)
                       for m in _MONTHS},
                },
                key="budget_grid",
            )

            if st.button("Save budget", type="primary"):
                rows = []
                for _, r in edited.iterrows():
                    aid = int(r["_account_id"])
                    for i, m in enumerate(_MONTHS, start=1):
                        rows.append({"account_id": aid, "month": i,
                                     "amount": float(r[m] or 0.0)})
                with get_session() as s:
                    n = budget_svc.bulk_set(s, budget_id, rows)
                st.success(f"Saved {n} budget lines.")
                st.rerun()


# ---- Budget vs Actual ------------------------------------------------------


with tab_va:
    budgets = _load_budgets()
    if not budgets:
        st.info("Create a budget first.")
    else:
        labels = {f"{b['name']} ({b['year']})": b["id"] for b in budgets}
        pick = st.selectbox("Budget", list(labels.keys()), key="va_pick")
        budget_id = labels[pick]
        sel_year = next(b["year"] for b in budgets if b["id"] == budget_id)

        c1, c2 = st.columns(2)
        ps = c1.date_input("Period start", value=date(sel_year, 1, 1), key="va_ps")
        pe = c2.date_input("Period end", value=date(sel_year, 12, 31), key="va_pe")

        with get_session() as s:
            rows = budget_svc.budget_vs_actual(
                s, budget_id, period_start=ps, period_end=pe)

        if not rows:
            st.caption("No budgeted accounts in this period.")
        else:
            df = pd.DataFrame(rows)

            tot_budget = df["budget_total"].sum()
            tot_actual = df["actual_total"].sum()
            tot_var = tot_actual - tot_budget
            ui.kpi_grid([
                {"label": "Total budget", "value": ui.money(tot_budget),
                 "color": "primary"},
                {"label": "Total actual", "value": ui.money(tot_actual),
                 "color": "accent"},
                {"label": "Total variance", "value": ui.money(tot_var),
                 "color": "danger" if tot_var > 0 else "success"},
            ])

            # Over-budget EXPENSE accounts (actual > budget) flagged.
            over = df[(df["type"] == "EXPENSE") & (df["variance"] > 0)]
            if not over.empty:
                names = ", ".join(over["name"].tolist())
                st.warning(f"Over-budget expense accounts: {names}")

            disp = df.copy()
            for col in ("budget_total", "actual_total", "variance"):
                disp[col] = disp[col].map(ui.money)
            disp["variance_pct"] = disp["variance_pct"].map(lambda v: f"{v:.1f}%")
            st.dataframe(disp, hide_index=True, width="stretch")

            # Grouped bar: budget vs actual per account.
            long_df = df.melt(
                id_vars=["name"], value_vars=["budget_total", "actual_total"],
                var_name="metric", value_name="amount",
            )
            long_df["metric"] = long_df["metric"].map(
                {"budget_total": "Budget", "actual_total": "Actual"})
            chart = (
                alt.Chart(long_df).mark_bar(
                    cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("name:N", title=None,
                            axis=alt.Axis(labelAngle=-30, labelColor="#64748B")),
                    y=alt.Y("amount:Q", title="₦",
                            axis=alt.Axis(format=",.0f", labelColor="#64748B",
                                          gridColor="#E5E7EB")),
                    color=alt.Color(
                        "metric:N",
                        scale=alt.Scale(domain=["Budget", "Actual"],
                                        range=["#1F3864", "#0EA5A4"]),
                        legend=alt.Legend(title=None, orient="top",
                                          labelColor="#64748B")),
                    xOffset="metric:N",
                    tooltip=["name", "metric",
                             alt.Tooltip("amount:Q", format=",.2f")],
                )
                .properties(height=300)
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart, use_container_width=True)

auth.render_logout_in_sidebar()
