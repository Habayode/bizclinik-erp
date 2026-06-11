"""Bank reconciliation — import statements, match against GL, finalise."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.importers.moniepoint_csv import parse_moniepoint_csv
from bizclinik_erp.models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    DocStatus,
    JournalEntry,
    JournalLine,
    StatementStatus,
)
from bizclinik_erp.services import recon as recon_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Bank Reconciliation · Trakit365 ERP",
                    layout="wide", page_icon="🔁")
ui.inject_brand()
auth.require_login()
from bizclinik_erp import gate as _gate; _gate.require_feature("bank_reconciliation", "Bank Reconciliation")
ui.hero("Bank Reconciliation",
        "Import bank statements · tick-and-tie to GL · finalise the period",
        badge="BR", right_label="Module", right_value="Cash matching")

tab_import, tab_recon, tab_history = st.tabs(
    ["📥 Import statement", "🔁 Reconcile", "📜 History"]
)


def _bank_options(session) -> dict[str, int]:
    return {f"{b.code} — {b.name}": b.id for b in session.execute(
        select(BankAccount).where(BankAccount.is_active == True)  # noqa: E712
        .order_by(BankAccount.code)
    ).scalars()}


# ---------------------------------------------------------------- import tab


with tab_import:
    with get_session() as s:
        bank_opts = _bank_options(s)
    if not bank_opts:
        st.info("Add a bank account first (Banking → Add bank account).")
    else:
        with st.form("import_stmt"):
            sel = st.selectbox("Bank", list(bank_opts.keys()), key="imp_bank")
            c1, c2 = st.columns(2)
            with c1:
                period_start = st.date_input(
                    "Period start", value=date.today().replace(day=1),
                    key="imp_pstart")
            with c2:
                period_end = st.date_input(
                    "Period end", value=date.today(), key="imp_pend")
            c3, c4 = st.columns(2)
            with c3:
                opening = st.number_input(
                    "Opening balance (₦)", value=0.0, format="%.2f",
                    key="imp_open")
            with c4:
                closing = st.number_input(
                    "Closing balance (₦)", value=0.0, format="%.2f",
                    key="imp_close")
            uploaded = st.file_uploader(
                "Moniepoint CSV", type=["csv"], key="imp_file",
                help="Columns: Date, Description, Reference, Debit, Credit, Balance",
            )
            submit = st.form_submit_button(
                "Import statement", type="primary")
        if submit:
            if not uploaded:
                st.error("Pick a CSV file to import.")
            elif period_end < period_start:
                st.error("Period end must be on or after period start.")
            else:
                try:
                    rows = parse_moniepoint_csv(uploaded.getvalue())
                except Exception as exc:
                    st.error(f"Could not parse CSV: {exc}")
                    rows = []
                if rows:
                    with get_session() as s:
                        stmt = recon_svc.create_statement(
                            s,
                            bank_account_id=bank_opts[sel],
                            period_start=period_start,
                            period_end=period_end,
                            opening_balance=opening,
                            closing_balance=closing,
                            source_file=uploaded.name,
                        )
                        n = recon_svc.import_statement_lines(
                            s, stmt.id, rows)
                    st.success(
                        f"Imported {n} line(s) into statement #{stmt.id}. "
                        "Jump to the Reconcile tab to match them.")
                else:
                    st.warning("No usable rows found in the CSV.")


# ------------------------------------------------------------ reconcile tab


with tab_recon:
    with get_session() as s:
        active_stmts = list(s.execute(
            select(BankStatement)
            .where(BankStatement.status != StatementStatus.LOCKED)
            .order_by(BankStatement.period_end.desc())
        ).scalars())
        stmt_opts = {
            f"#{st_.id} · {st_.bank_account.code} · "
            f"{st_.period_start:%Y-%m-%d} → {st_.period_end:%Y-%m-%d} "
            f"({st_.status.value})": st_.id
            for st_ in active_stmts
        }

    if not stmt_opts:
        st.info("No statements yet. Import one from the previous tab.")
    else:
        chosen_label = st.selectbox(
            "Active statement", list(stmt_opts.keys()), key="rec_pick")
        sid = stmt_opts[chosen_label]

        # ---- summary block ----
        with get_session() as s:
            summary = recon_svc.reconciliation_summary(s, sid)
        ui.kpi_grid([
            {"label": "Matched", "value": str(summary["matched_count"]),
             "color": "accent", "icon": "✓"},
            {"label": "Matched total", "value": ui.money(summary["matched_total"]),
             "color": "primary"},
            {"label": "Unreconciled (statement)",
             "value": ui.money(summary["unreconciled_statement_total"]),
             "color": "warning"},
            {"label": "Unreconciled (GL)",
             "value": ui.money(summary["unreconciled_gl_total"]),
             "color": "warning"},
            {"label": "Computed diff",
             "value": ui.money(summary["computed_diff"]),
             "color": "success" if abs(summary["computed_diff"]) < 0.01 else "danger"},
        ])

        c_auto, c_final = st.columns([1, 1])
        with c_auto:
            day_tol = st.number_input(
                "Day tolerance", min_value=0, max_value=14, value=3,
                key="rec_tol")
            if st.button("🔮 Auto-match", type="primary", key="rec_auto"):
                with get_session() as s:
                    res = recon_svc.auto_match(
                        s, sid, day_tolerance=int(day_tol))
                st.success(
                    f"Matched {res['matched']}. "
                    f"Unmatched statement: {res['unmatched_statement']}, "
                    f"unmatched GL: {res['unmatched_gl']}.")
                st.rerun()
        with c_final:
            if summary["unreconciled_statement_count"] == 0 \
                    and summary["unreconciled_gl_count"] == 0:
                if st.button("🔒 Finalise (mark RECONCILED)", key="rec_fin"):
                    with get_session() as s:
                        recon_svc.finalize(s, sid)
                    st.success("Statement marked RECONCILED.")
                    st.rerun()
            else:
                st.caption(
                    "Resolve the unreconciled rows before finalising "
                    "(match them, exclude them, or post the missing JE).")

        # ---- side-by-side panes ----
        st.divider()
        with get_session() as s:
            stmt = s.get(BankStatement, sid)
            bank = stmt.bank_account
            stmt_rows = [{
                "id": l.id,
                "date": l.txn_date,
                "description": l.description,
                "amount": l.amount,
                "reference": l.reference or "",
                "status": ("matched" if l.matched_je_line_id
                           else ("excluded" if l.is_excluded
                                 else "unmatched")),
            } for l in stmt.lines]

            gl_q = (
                select(JournalLine, JournalEntry)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .where(
                    JournalLine.account_id == bank.gl_account_id,
                    JournalEntry.status == DocStatus.POSTED,
                    JournalEntry.entry_date >= stmt.period_start
                    - timedelta(days=int(day_tol)),
                    JournalEntry.entry_date <= stmt.period_end
                    + timedelta(days=int(day_tol)),
                )
                .order_by(JournalEntry.entry_date, JournalLine.id)
            )
            matched_jl_ids = {l.matched_je_line_id for l in stmt.lines
                              if l.matched_je_line_id is not None}
            gl_rows = []
            unmatched_gl_for_dropdown: dict[str, int] = {}
            for jl, je in s.execute(gl_q):
                signed = round(jl.debit - jl.credit, 2)
                row_status = ("matched" if jl.id in matched_jl_ids
                              else "unmatched")
                gl_rows.append({
                    "id": jl.id, "date": je.entry_date,
                    "entry_no": je.entry_no,
                    "memo": jl.memo or je.memo,
                    "amount": signed,
                    "status": row_status,
                })
                if row_status == "unmatched":
                    label = (f"#{jl.id} · {je.entry_date:%Y-%m-%d} · "
                             f"{je.entry_no} · ₦{signed:,.2f}")
                    unmatched_gl_for_dropdown[label] = jl.id

        c_left, c_right = st.columns(2)
        with c_left:
            st.subheader("Statement lines")
            st.dataframe(pd.DataFrame(stmt_rows), hide_index=True,
                          width="stretch")
        with c_right:
            st.subheader(f"GL lines on {bank.code}")
            st.dataframe(pd.DataFrame(gl_rows), hide_index=True,
                          width="stretch")

        # ---- per-row manual match ----
        st.divider()
        st.subheader("Match manually")
        unmatched_stmt_rows = [r for r in stmt_rows if r["status"] == "unmatched"]
        if not unmatched_stmt_rows:
            st.success("All statement rows are accounted for.")
        elif not unmatched_gl_for_dropdown:
            st.info("Nothing left in GL to match against. "
                    "Post the missing JE (Banking → Charge / Receipt / etc.) "
                    "or exclude the row.")
        else:
            for row in unmatched_stmt_rows:
                cols = st.columns([3, 4, 1])
                cols[0].write(
                    f"**{row['date']:%Y-%m-%d}** · ₦{row['amount']:,.2f}")
                cols[0].caption(row["description"])
                pick_key = f"pick_{row['id']}"
                pick = cols[1].selectbox(
                    "GL line", ["—"] + list(unmatched_gl_for_dropdown.keys()),
                    key=pick_key, label_visibility="collapsed")
                if cols[2].button("Match", key=f"btn_{row['id']}"):
                    if pick == "—":
                        st.error("Pick a GL line first.")
                    else:
                        with get_session() as s:
                            recon_svc.manual_match(
                                s, row["id"],
                                unmatched_gl_for_dropdown[pick])
                        st.success("Matched.")
                        st.rerun()


# ----------------------------------------------------------------- history tab


with tab_history:
    with get_session() as s:
        rows = []
        for st_ in s.execute(
                select(BankStatement).order_by(BankStatement.id.desc())
        ).scalars():
            bank = st_.bank_account
            rows.append({
                "id": st_.id,
                "bank": f"{bank.code} — {bank.name}",
                "period_start": st_.period_start,
                "period_end": st_.period_end,
                "opening": st_.opening_balance,
                "closing": st_.closing_balance,
                "status": st_.status.value,
                "lines": len(st_.lines),
                "source_file": st_.source_file or "",
                "imported_at": st_.imported_at,
            })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No statements imported yet.")


auth.render_logout_in_sidebar()
