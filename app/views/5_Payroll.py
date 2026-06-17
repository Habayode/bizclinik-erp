"""Payroll: employees, payroll runs, payslips."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import BankAccount, Employee, PayrollPayslip, PayrollRun
from bizclinik_erp.services import payroll as pr_svc
from bizclinik_erp.services import approvals
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Payroll · Trakit365 ERP", layout="wide",
                    page_icon="👥")
ui.inject_brand()
auth.require_login()
auth.require_perm("run.payroll")
ui.hero("Payroll", "Employees · runs · payslips",
         badge="PR", right_label="Module", right_value="HR")

_u = auth.current_user() or {}
UID, ROLE = _u.get("user_id"), _u.get("role")

tab_emp, tab_run, tab_slip = st.tabs(["👤 Employees", "🧮 Run payroll", "🧾 Payslips"])


with tab_emp:
    with get_session() as s:
        emps = s.execute(select(Employee).order_by(Employee.code)).scalars().all()
        rows = [{
            "code": e.code, "name": e.name, "email": e.email,
            "monthly_gross": e.monthly_gross,
            "paye_rate": e.paye_rate, "pension_rate": e.pension_rate,
            "pension_employer_rate": e.pension_employer_rate,
            "active": e.is_active,
        } for e in emps]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"monthly_gross": ui.money_col("monthly_gross")})

    st.divider()
    st.subheader("Add employee")
    with st.form("emp"):
        code = st.text_input("Code")
        name = st.text_input("Name")
        email = st.text_input("Email")
        gross = st.number_input("Monthly gross (₦)", min_value=0.0, format="%.2f")
        paye = st.number_input("Flat PAYE override (0 = graduated, recommended)",
                                min_value=0.0, max_value=1.0, format="%.3f", value=0.0,
                                help="Leave 0 and PAYE is computed on the graduated "
                                     "CITA bands automatically. Only set a flat "
                                     "effective rate to override that.")
        pen_emp = st.number_input("Employee pension rate",
                                     min_value=0.0, max_value=1.0, format="%.3f", value=0.08)
        pen_er = st.number_input("Employer pension rate",
                                    min_value=0.0, max_value=1.0, format="%.3f", value=0.10)
        submit = st.form_submit_button("Save", type="primary")
    if submit:
        if not code or not name:
            st.error("Code and name required.")
        else:
            with get_session() as s:
                s.add(Employee(code=code, name=name, email=email or None,
                                monthly_gross=gross, paye_rate=paye,
                                pension_rate=pen_emp, pension_employer_rate=pen_er))
            st.success(f"Added {code}")


with tab_run:
    with get_session() as s:
        emps = s.execute(select(Employee).where(Employee.is_active == True)  # noqa: E712
                          .order_by(Employee.code)).scalars().all()
        bank_opts = {f"{b.code} — {b.name}": b.id
                      for b in s.execute(select(BankAccount).order_by(BankAccount.code)).scalars()}
    if not emps:
        st.info("Add employees first.")
    elif not bank_opts:
        st.info("Need a bank account.")
    else:
        with st.form("run"):
            c1, c2, c3 = st.columns(3)
            p_start = c1.date_input("Period start",
                                      value=date.today().replace(day=1))
            p_end = c2.date_input("Period end", value=date.today())
            pay_date = c3.date_input("Pay date", value=date.today())
            sel_bank = st.selectbox("Bank", list(bank_opts.keys()))

            df = pd.DataFrame([{"employee_id": e.id, "name": e.name,
                                 "gross": e.monthly_gross,
                                 "other_deductions": 0.0} for e in emps])
            grid = st.data_editor(df, hide_index=True, disabled=["employee_id", "name"])
            notes = st.text_area("Notes")
            submit = st.form_submit_button("Run payroll", type="primary")
        if submit:
            input_dicts = []
            for _, row in grid.iterrows():
                input_dicts.append({
                    "employee_id": int(row["employee_id"]),
                    "gross": float(row["gross"] or 0),
                    "other_deductions": float(row["other_deductions"] or 0),
                })
            total_gross = round(sum(d["gross"] for d in input_dicts), 2)
            payload = {
                "period_start": p_start.isoformat(), "period_end": p_end.isoformat(),
                "pay_date": pay_date.isoformat(),
                "bank_account_id": bank_opts[sel_bank], "notes": notes or None,
                "inputs": input_dicts,
            }
            with get_session() as s:
                res = approvals.gate(
                    s, doc_type="PAYROLL", amount=total_gross,
                    title=f"Payroll {p_start:%b %Y} (₦{total_gross:,.0f})",
                    payload=payload, user_id=UID, role=ROLE)
            if res["status"] == "pending":
                lim = res.get("limit")
                lim_txt = f"₦{lim:,.0f}" if lim is not None else "your"
                st.warning(
                    f"🔒 Gross ₦{total_gross:,.0f} is above your approval limit "
                    f"({lim_txt}) — submitted for approval (request "
                    f"#{res['request_id']}). It posts once approved on the "
                    "**Approvals** page.", icon="🔒")
            else:
                st.success(f"Payroll {res['ref']} posted.")


with tab_slip:
    with get_session() as s:
        runs = s.execute(select(PayrollRun).order_by(PayrollRun.pay_date.desc())).scalars().all()
        opts = {f"{r.number} — {r.period_start} → {r.period_end}": r.id for r in runs}
    if opts:
        sel = st.selectbox("Run", list(opts.keys()), key="slip_sel")
        with get_session() as s:
            slips = s.execute(select(PayrollPayslip).where(
                PayrollPayslip.run_id == opts[sel]
            )).scalars().all()
            rows = [{
                "employee": p.employee.name if p.employee else "",
                "gross": p.gross, "PAYE": p.paye,
                "pension_emp": p.pension_employee,
                "pension_er": p.pension_employer,
                "other": p.other_deductions, "net_pay": p.net_pay,
            } for p in slips]
        ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={c: ui.money_col(c) for c in
                                    ("gross", "PAYE", "pension_emp",
                                     "pension_er", "other", "net_pay")})
    else:
        st.info("Run payroll to generate payslips.")

auth.render_logout_in_sidebar()
