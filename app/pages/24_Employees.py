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

st.set_page_config(page_title="Employees · BizClinik ERP", layout="wide",
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
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.markdown("##### Activate / deactivate")
        cc1, cc2 = st.columns([1, 1])
        eid = cc1.number_input("Employee id", min_value=1, step=1, key="emp_toggle")
        if cc2.button("Toggle active", key="emp_toggle_btn"):
            with get_session() as s:
                emp = next((e for e in hr.list_employees(s) if e.id == int(eid)), None)
                if emp:
                    hr.set_employee_active(s, int(eid), not emp.is_active)
                    st.success(f"{emp.name} → {'active' if not emp.is_active else 'inactive'}")
                    st.rerun()
                else:
                    st.error("No such employee id.")
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
                    st.success(f"Added {emp.name} ({emp.code})")
                st.rerun()

auth.render_logout_in_sidebar()
