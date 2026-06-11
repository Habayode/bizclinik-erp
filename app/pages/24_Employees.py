"""Employees — staff directory (HR)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp.services import hr
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="Employees · Trakit365 ERP", layout="wide",
                    page_icon="🧑‍💼")
ui.inject_brand()
auth.require_login()
ui.hero("Employees", "Staff directory", badge="EM",
        right_label="Module", right_value="HR")

with get_session() as s:
    hc = hr.headcount(s)
c1, c2, c3 = st.columns(3)
c1.metric("Total staff", hc["total"])
c2.metric("Active", hc["active"])
c3.metric("Inactive", hc["inactive"])

st.divider()
tab_list, tab_add = st.tabs(["👥 Directory", "➕ Add employee"])

with tab_list:
    show_inactive = st.checkbox("Show inactive", value=False)
    with get_session() as s:
        emps = hr.list_employees(s, active_only=not show_inactive)
        rows = [{
            "id": e.id, "code": e.code, "name": e.name,
            "department": e.department or "", "title": e.job_title or "",
            "type": e.employment_type or "", "email": e.email or "",
            "monthly_gross": e.monthly_gross, "leave/yr": e.annual_leave_days,
            "active": e.is_active,
        } for e in emps]
    if rows:
        sel_e = ui.pick_row(
            pd.DataFrame(rows), key="emp_pick",
            column_config={"monthly_gross": ui.money_col("monthly gross")})
        if sel_e is not None:
            action = "Deactivate" if sel_e["active"] else "Activate"
            confirm = st.checkbox(
                f"I confirm — {action.lower()} {sel_e['name']} "
                f"({'they stop appearing in Payroll and Leave' if sel_e['active'] else 'they return to Payroll and Leave'}).",
                key="emp_confirm")
            if st.button(f"{action} {sel_e['name']}", key="emp_toggle_btn",
                         disabled=not confirm):
                with get_session() as s:
                    hr.set_employee_active(s, int(sel_e["id"]),
                                           not bool(sel_e["active"]))
                ui.flash(f"{sel_e['name']} → "
                         f"{'inactive' if sel_e['active'] else 'active'}")
                st.rerun()
        else:
            st.caption("Select an employee to activate/deactivate.")
    else:
        st.caption("No employees yet — add one in the next tab.")

with tab_add:
    with st.form("new_emp"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Full name *")
        dept = c2.text_input("Department")
        title = c3.text_input("Job title")
        c4, c5, c6 = st.columns(3)
        email = c4.text_input("Email")
        phone = c5.text_input("Phone")
        etype = c6.selectbox("Employment type",
                             ["full-time", "part-time", "contract", "intern"])
        c7, c8, c9 = st.columns(3)
        gross = c7.number_input("Monthly gross (₦)", min_value=0.0, step=10000.0)
        paye = c8.number_input("PAYE rate", min_value=0.0, max_value=1.0,
                               step=0.01, value=0.0,
                               help="Effective PAYE rate (0–1). Leave 0 to set later.")
        leave_days = c9.number_input("Annual leave days", min_value=0.0,
                                     step=1.0, value=20.0)
        hire = st.date_input("Hire date", value=date.today())
        if st.form_submit_button("Add employee", type="primary"):
            if not name.strip():
                st.error("Name is required.")
            else:
                with get_session() as s:
                    emp = hr.create_employee(
                        s, name=name, email=email or None, phone=phone or None,
                        department=dept or None, job_title=title or None,
                        employment_type=etype, monthly_gross=gross,
                        paye_rate=paye, annual_leave_days=leave_days,
                        hire_date=hire)
                    ui.flash(f"Added {emp.name} ({emp.code})")
                st.rerun()

auth.render_logout_in_sidebar()
