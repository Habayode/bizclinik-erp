"""Recurring transactions — rent, subscriptions, standing orders, payroll-like JEs."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (
    Account,
    Customer,
    RecurringFrequency,
    RecurringKind,
    RecurringTemplate,
    Supplier,
)
from bizclinik_erp.services import recurring as rec_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth


st.set_page_config(page_title="Recurring · Trakit365 ERP", layout="wide",
                   page_icon="🔁")
ui.inject_brand()
auth.require_login()
auth.require_perm("post.journal")
from bizclinik_erp import gate as _gate; _gate.require_feature("recurring", "Recurring Transactions")
ui.hero("Recurring Transactions",
        "Rent · subscriptions · standing orders · payroll-like JEs",
        badge="RC", right_label="Module", right_value="Automation")


# ----- shared loaders -------------------------------------------------------


def _customer_options(session) -> dict[str, int]:
    rows = session.execute(select(Customer).order_by(Customer.name)).scalars().all()
    return {f"{c.code} — {c.name}": c.id for c in rows}


def _supplier_options(session) -> dict[str, int]:
    rows = session.execute(select(Supplier).order_by(Supplier.name)).scalars().all()
    return {f"{s.code} — {s.name}": s.id for s in rows}


def _account_options(session, *, postable_only: bool = True) -> dict[str, int]:
    q = select(Account).order_by(Account.code)
    rows = session.execute(q).scalars().all()
    if postable_only:
        rows = [a for a in rows if a.is_postable]
    return {f"{a.code} — {a.name}": a.id for a in rows}


def _all_templates_df(session) -> pd.DataFrame:
    rows = session.execute(
        select(RecurringTemplate).order_by(RecurringTemplate.next_run_date)
    ).scalars().all()
    return pd.DataFrame([{
        "code": t.code,
        "name": t.name,
        "kind": t.kind.value,
        "frequency": t.frequency.value,
        "next_run": t.next_run_date,
        "end_date": t.end_date,
        "active": t.is_active,
        "last_run_at": t.last_run_at,
        "last_run_doc": t.last_run_doc,
    } for t in rows])


tab_list, tab_new, tab_run, tab_hist = st.tabs(
    ["📋 Templates", "➕ New template", "🔄 Run due now", "📜 History"]
)


# ----- Templates tab --------------------------------------------------------


with tab_list:
    st.subheader("All recurring templates")
    with get_session() as s:
        df = _all_templates_df(s)
    if df.empty:
        st.info("No recurring templates yet. Add one on the **New template** tab.")
    else:
        ui.dataframe(df, hide_index=True, width="stretch")


# ----- New template tab -----------------------------------------------------


with tab_new:
    st.subheader("Create a recurring template")
    kind_choice = st.selectbox(
        "Kind",
        ["INVOICE", "BILL", "JOURNAL"],
        help="What transaction will be materialised each cycle?",
        key="rec_kind",
    )

    with get_session() as s:
        cust_opts = _customer_options(s)
        sup_opts = _supplier_options(s)
        acct_opts = _account_options(s)

    with st.form("new_recurring_template"):
        c1, c2 = st.columns(2)
        code = c1.text_input("Code", placeholder="e.g. RENT-MAIN")
        name = c2.text_input("Name", placeholder="e.g. Office rent — main shop")

        # Kind-specific inputs
        customer_id = supplier_id = expense_account_id = None
        line_description = ""
        qty = unit_price = unit_cost = tax_rate = 0.0
        memo = ""
        je_grid = None

        if kind_choice == "INVOICE":
            if not cust_opts:
                st.warning("No customers exist yet. Add one on the Sales / Settings page first.")
            sel_cust = st.selectbox("Customer", list(cust_opts.keys()) or [""])
            customer_id = cust_opts.get(sel_cust)
            line_description = st.text_input("Line description",
                                              placeholder="Monthly subscription")
            c3, c4, c5 = st.columns(3)
            qty = c3.number_input("Qty", min_value=0.0, value=1.0, step=1.0)
            unit_price = c4.number_input("Unit price (₦)", min_value=0.0,
                                          value=0.0, format="%.2f")
            tax_rate = c5.number_input("Tax rate (decimal)", min_value=0.0,
                                        max_value=1.0, value=0.075, format="%.3f")

        elif kind_choice == "BILL":
            if not sup_opts:
                st.warning("No suppliers exist yet. Add one on the Purchase / Settings page first.")
            sel_sup = st.selectbox("Supplier", list(sup_opts.keys()) or [""])
            supplier_id = sup_opts.get(sel_sup)
            line_description = st.text_input("Line description", placeholder="Monthly rent")
            c3, c4, c5 = st.columns(3)
            qty = c3.number_input("Qty", min_value=0.0, value=1.0, step=1.0, key="bill_qty")
            unit_cost = c4.number_input("Unit cost (₦)", min_value=0.0,
                                         value=0.0, format="%.2f")
            tax_rate = c5.number_input("Tax rate (decimal)", min_value=0.0,
                                        max_value=1.0, value=0.075, format="%.3f",
                                        key="bill_tax")
            sel_exp = st.selectbox("Expense account",
                                    [""] + list(acct_opts.keys()),
                                    help="Where the debit lands. Leave blank for default.")
            expense_account_id = acct_opts.get(sel_exp) if sel_exp else None

        else:  # JOURNAL
            memo = st.text_input("JE memo",
                                  placeholder="Standing order — bank")
            st.caption("Add the JE lines. Use ONE of debit or credit per row, "
                       "and either account_id or account_code.")
            seed = pd.DataFrame([
                {"account_code": "", "account_id": None,
                 "debit": 0.0, "credit": 0.0, "memo": ""},
                {"account_code": "", "account_id": None,
                 "debit": 0.0, "credit": 0.0, "memo": ""},
            ])
            je_grid = st.data_editor(
                seed, num_rows="dynamic", key="je_lines",
                column_config={
                    "account_code": st.column_config.TextColumn(
                        "Account code", help="e.g. 6200"),
                    "account_id": st.column_config.NumberColumn(
                        "Account ID", help="Use code OR id, not both"),
                    "debit": st.column_config.NumberColumn(
                        "Debit (₦)", min_value=0.0, format="%.2f"),
                    "credit": st.column_config.NumberColumn(
                        "Credit (₦)", min_value=0.0, format="%.2f"),
                },
            )

        st.divider()
        c6, c7, c8 = st.columns(3)
        freq_choice = c6.selectbox("Frequency", ["MONTHLY", "QUARTERLY", "ANNUAL"])
        next_run = c7.date_input("Next run date", value=date.today())
        end_choice = c8.date_input("End date (optional)",
                                    value=None, format="YYYY-MM-DD")

        submit = st.form_submit_button("Create template", type="primary")

    if submit:
        try:
            kind_enum = RecurringKind(kind_choice)
            freq_enum = RecurringFrequency(freq_choice)
            payload: dict = {}
            if kind_enum == RecurringKind.INVOICE:
                payload = {
                    "customer_id": customer_id,
                    "line_description": line_description,
                    "qty": qty,
                    "unit_price": unit_price,
                    "tax_rate": tax_rate,
                }
            elif kind_enum == RecurringKind.BILL:
                payload = {
                    "supplier_id": supplier_id,
                    "line_description": line_description,
                    "qty": qty,
                    "unit_cost": unit_cost,
                    "tax_rate": tax_rate,
                    "expense_account_id": expense_account_id,
                }
            else:
                je_lines = []
                if je_grid is not None:
                    for _, row in je_grid.iterrows():
                        dr = float(row.get("debit") or 0)
                        cr = float(row.get("credit") or 0)
                        if dr == 0 and cr == 0:
                            continue
                        je_lines.append({
                            "account_id": int(row["account_id"])
                                if pd.notna(row.get("account_id")) else None,
                            "account_code": str(row.get("account_code") or "").strip() or None,
                            "debit": dr,
                            "credit": cr,
                            "memo": str(row.get("memo") or "").strip() or None,
                        })
                payload = {"memo": memo, "lines": je_lines}

            with get_session() as s:
                tpl = rec_svc.create_template(
                    s, kind=kind_enum, code=code, name=name,
                    frequency=freq_enum, next_run_date=next_run,
                    payload=payload,
                    end_date=end_choice if end_choice else None,
                )
            st.success(f"Created template {tpl.code} ({tpl.kind.value}) — "
                       f"next run {tpl.next_run_date}.")
        except Exception as e:
            st.error(f"Could not create template: {e}")


# ----- Run due now tab ------------------------------------------------------


with tab_run:
    st.subheader("Run due templates")
    as_of = st.date_input("As of", value=date.today(), key="run_as_of")

    with get_session() as s:
        due = rec_svc.due_templates(s, as_of=as_of)
        due_rows = [{
            "code": t.code, "name": t.name, "kind": t.kind.value,
            "next_run": t.next_run_date,
        } for t in due]
    if due_rows:
        st.write(f"**{len(due_rows)}** template(s) due:")
        ui.dataframe(pd.DataFrame(due_rows), hide_index=True, width="stretch")
    else:
        st.info("No templates due as of that date.")

    if st.button("Run due templates", type="primary", disabled=not due_rows):
        with get_session() as s:
            result = rec_svc.run_due(s, as_of=as_of)
        st.success(
            f"Materialised {result['materialized']} txn(s) — "
            f"{result['skipped']} skipped."
        )
        if result.get("skipped_details"):
            st.warning("Some templates were skipped (not lost — they'll run "
                       "once the issue is cleared):")
            ui.dataframe(pd.DataFrame(result["skipped_details"]),
                         hide_index=True, width="stretch")
        if result["docs"]:
            st.write("Documents posted:")
            for d in result["docs"]:
                st.write(f"  • `{d}`")


# ----- History tab ----------------------------------------------------------


with tab_hist:
    st.subheader("Run history")
    with get_session() as s:
        rows = s.execute(
            select(RecurringTemplate).order_by(
                RecurringTemplate.last_run_at.desc().nullslast()
            )
        ).scalars().all()
        hist = [{
            "code": t.code,
            "name": t.name,
            "kind": t.kind.value,
            "last_run_at": t.last_run_at,
            "last_run_doc": t.last_run_doc,
            "next_run": t.next_run_date,
            "active": t.is_active,
        } for t in rows]
    if hist:
        ui.dataframe(pd.DataFrame(hist), hide_index=True, width="stretch")
    else:
        st.info("No history yet.")


auth.render_logout_in_sidebar()
