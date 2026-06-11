"""Leave management — requests, approvals, and balances (HR)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp.models import LeaveStatus, LeaveType
from bizclinik_erp.services import hr
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="Leave · Trakit365 ERP", layout="wide",
                    page_icon="🌴")
ui.inject_brand()
auth.require_login()
ui.hero("Leave", "Requests · approvals · balances", badge="LV",
        right_label="Module", right_value="HR")

uid = auth.current_user_id()

with get_session() as s:
    summ = hr.leave_summary(s)
c1, c2 = st.columns(2)
c1.metric("Pending approval", summ["pending"])
c2.metric("Approved (all-time)", summ["approved"])

tab_req, tab_appr, tab_bal = st.tabs(
    ["📝 Request", "✅ Approvals", "📊 Balances"])


def _employee_options(s):
    return {f"{e.name} ({e.code})": e.id for e in hr.list_employees(s, active_only=True)}


# --------------------------------------------------------------------------- #
# Request                                                                      #
# --------------------------------------------------------------------------- #
with tab_req:
    with get_session() as s:
        emp_opts = _employee_options(s)
    if not emp_opts:
        st.info("Add an employee first (Employees page).")
    else:
        with st.form("new_leave"):
            c1, c2 = st.columns(2)
            emp_label = c1.selectbox("Employee", list(emp_opts.keys()))
            ltype = c2.selectbox("Leave type", [t.value for t in LeaveType])
            c3, c4 = st.columns(2)
            start = c3.date_input("Start date", value=date.today())
            end = c4.date_input("End date", value=date.today())
            reason = st.text_input("Reason")
            if st.form_submit_button("Submit request", type="primary"):
                if end < start:
                    st.error("End date cannot be before start date.")
                else:
                    with get_session() as s:
                        req = hr.request_leave(
                            s, employee_id=emp_opts[emp_label],
                            leave_type=LeaveType(ltype), start_date=start,
                            end_date=end, reason=reason or None)
                    st.success(f"Requested {req.days:.0f} day(s) — pending approval.")
                    st.rerun()

    st.divider()
    with get_session() as s:
        reqs = hr.list_leave(s)
        emp_names = {e.id: e.name for e in hr.list_employees(s)}
        rows = [{"id": r.id, "employee": emp_names.get(r.employee_id, "?"),
                 "type": r.leave_type.value, "from": r.start_date, "to": r.end_date,
                 "days": r.days, "status": r.status.value} for r in reqs]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# --------------------------------------------------------------------------- #
# Approvals                                                                    #
# --------------------------------------------------------------------------- #
with tab_appr:
    with get_session() as s:
        pending = hr.list_leave(s, status=LeaveStatus.PENDING)
        emp_names = {e.id: e.name for e in hr.list_employees(s)}
        prows = [{"id": r.id, "employee": emp_names.get(r.employee_id, "?"),
                  "type": r.leave_type.value, "from": r.start_date,
                  "to": r.end_date, "days": r.days,
                  "reason": r.reason or ""} for r in pending]
    if prows:
        st.dataframe(pd.DataFrame(prows), hide_index=True, width="stretch")
        ac1, ac2, ac3 = st.columns([1, 1, 1])
        req_id = ac1.number_input("Request id", min_value=1, step=1, key="ap_req")
        if ac2.button("Approve", key="ap_yes", type="primary"):
            with get_session() as s:
                hr.decide_leave(s, int(req_id), approve=True, approver_user_id=uid)
            st.success(f"Request {int(req_id)} approved."); st.rerun()
        if ac3.button("Reject", key="ap_no"):
            with get_session() as s:
                hr.decide_leave(s, int(req_id), approve=False, approver_user_id=uid)
            st.warning(f"Request {int(req_id)} rejected."); st.rerun()
    else:
        st.caption("No pending requests. 🎉")


# --------------------------------------------------------------------------- #
# Balances                                                                     #
# --------------------------------------------------------------------------- #
with tab_bal:
    year = st.number_input("Year", min_value=2000, max_value=2100,
                           value=date.today().year, step=1)
    with get_session() as s:
        emps = hr.list_employees(s, active_only=True)
        brows = []
        for e in emps:
            bal = hr.leave_balance(s, e.id, year=int(year))
            brows.append({"code": e.code, "name": e.name,
                          "entitlement": bal["entitlement"],
                          "taken (annual)": bal["taken"],
                          "remaining": bal["remaining"]})
    if brows:
        st.dataframe(pd.DataFrame(brows), hide_index=True, width="stretch")
        st.caption("Balance = annual entitlement − APPROVED annual leave taken "
                   "in the selected year. Sick/unpaid/other leave is tracked but "
                   "does not reduce the annual balance.")
    else:
        st.caption("No active employees.")

auth.render_logout_in_sidebar()
