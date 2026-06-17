"""Teachers and Dashboard — teaching-staff directory and school KPIs.

Phase 5 of the school layer (GL-free). A teacher profile is a school overlay on
an existing Employee (qualification, registration, subjects, class assignments)
— payroll identity stays on Employee. The Dashboard tab rolls up enrolment,
staff and the fee position (billed / collected / outstanding) read-only from the
data captured by earlier phases and the sales/AR engine; nothing here posts to
the GL.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (AcademicSession, Employee, StaffType,
                                  TeacherProfile)
from bizclinik_erp.services import school_staff
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Teachers · Trakit365 ERP", layout="wide",
                   page_icon="👩‍🏫")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")
ui.hero("Teachers and Dashboard", "Teaching staff · school KPIs",
         badge="TC", right_label="Module", right_value="School")

tab_staff, tab_dash = st.tabs(["👩‍🏫 Teaching staff", "📊 Dashboard"])

_STAFF_OPTS = {"Teaching": "TEACHING", "Non-teaching": "NON_TEACHING"}


# ---- Teaching staff --------------------------------------------------------
with tab_staff:
    st.caption("Assign a teaching profile to an existing employee. Payroll and "
               "HR identity stay on the employee record — this only adds school "
               "metadata (subjects, classes, registration). One profile per "
               "employee; re-assigning updates it.")
    with get_session() as s:
        rows = school_staff.list_teachers(s)
        emp_opts = {f"{e.code} — {e.name}": e.id for e in s.execute(
            select(Employee).where(Employee.is_active == True)  # noqa: E712
            .order_by(Employee.name)).scalars()}
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if not emp_opts:
        st.info("Add an employee first (HR · Employees).")
    else:
        with st.form("teacher"):
            emp = st.selectbox("Employee", list(emp_opts.keys()))
            c1, c2 = st.columns(2)
            staff_label = c1.selectbox("Staff type", list(_STAFF_OPTS.keys()))
            qual = c2.text_input("Qualification", placeholder="B.Ed Mathematics")
            c3, c4 = st.columns(2)
            reg = c3.text_input("Registration number", placeholder="TRCN/12345")
            subjects = c4.text_input("Subjects taught",
                                     placeholder="Maths, Further Maths")
            classes = st.text_input("Classes assigned",
                                    placeholder="JSS1A, JSS2B")
            if st.form_submit_button("Save profile", type="primary"):
                try:
                    with get_session() as s:
                        school_staff.upsert_teacher_profile(
                            s, employee_id=emp_opts[emp],
                            staff_type=_STAFF_OPTS[staff_label],
                            qualification=qual or None,
                            registration_number=reg or None,
                            subjects_taught=subjects or None,
                            classes_assigned=classes or None)
                    ui.flash("Teacher profile saved."); st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ---- Dashboard -------------------------------------------------------------
with tab_dash:
    st.caption("Read-only snapshot — enrolment, staff and the fee position. "
               "Pick a session to scope the fee figures, or leave on "
               "**All sessions** for the cumulative position.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in s.execute(
            select(AcademicSession).order_by(
                AcademicSession.session_code)).scalars()}
    sess_label = st.selectbox("Academic session",
                              ["All sessions"] + list(sess_opts.keys()))
    sess_id = None if sess_label == "All sessions" else sess_opts[sess_label]
    with get_session() as s:
        kpi = school_staff.school_dashboard(s, academic_session_id=sess_id)

    c1, c2, c3 = st.columns(3)
    c1.metric("Active students", f"{kpi['total_students']:,}")
    c2.metric("Teaching staff", f"{kpi['total_teachers']:,}")
    c3.metric("Defaulters", f"{kpi['defaulter_count']:,}")
    c4, c5, c6 = st.columns(3)
    c4.metric("Fees billed", f"{kpi['fees_billed']:,.2f}")
    c5.metric("Fees collected", f"{kpi['fees_collected']:,.2f}")
    c6.metric("Fees outstanding", f"{kpi['fees_outstanding']:,.2f}")

    st.subheader("Enrolment by class")
    if kpi["enrolment_by_class"]:
        st.dataframe(pd.DataFrame(kpi["enrolment_by_class"]),
                     hide_index=True, width="stretch")
    else:
        st.info("No active students enrolled yet.")


auth.render_logout_in_sidebar()
