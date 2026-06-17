"""School Results — enter per-subject term results and preview a report card.

Phase 4 of the school layer. Pure academic records: entering a result computes
total = CA + exam and a letter grade, and posts NOTHING to the GL. The report
card tab rolls a student's subjects up into an average for a (session, term).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (AcademicSession, Employee, SchoolClass,
                                  Student, StudentStatus)
from bizclinik_erp.services import school_ops
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="School Results · Trakit365 ERP", layout="wide",
                   page_icon="📝")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")
ui.hero("School Results", "Enter results · report-card preview",
         badge="RS", right_label="Module", right_value="School")

_TERM_OPTS = {"Term 1": 1, "Term 2": 2, "Term 3": 3}

tab_enter, tab_card = st.tabs(["✍️ Enter result", "🧾 Report card"])


def _student_label(st_) -> str:
    return f"{st_.admission_no} — {st_.first_name} {st_.last_name}"


# ---- Enter result ----------------------------------------------------------
with tab_enter:
    st.caption("Total = CA + Exam; the grade is derived automatically. "
               "Nothing here posts to the ledger.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in s.execute(
            select(AcademicSession).where(AcademicSession.is_active == True)  # noqa: E712
            .order_by(AcademicSession.session_code)).scalars()}
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).order_by(SchoolClass.class_code)).scalars()}
        students = s.execute(select(Student).where(
            Student.status == StudentStatus.ACTIVE)
            .order_by(Student.last_name, Student.first_name)).scalars().all()
        stu_opts = {_student_label(st_): st_.id for st_ in students}
        teach_opts = {f"{e.code} — {e.name}": e.id for e in s.execute(
            select(Employee).where(Employee.is_active == True)  # noqa: E712
            .order_by(Employee.name)).scalars()}
    if not (sess_opts and stu_opts):
        st.info("Add an academic session and enrol a student first.")
    else:
        with st.form("result"):
            stu = st.selectbox("Student", list(stu_opts.keys()))
            c1, c2, c3 = st.columns(3)
            sess = c1.selectbox("Session", list(sess_opts.keys()))
            cls = c2.selectbox("Class", ["—"] + list(cls_opts.keys()))
            term_label = c3.selectbox("Term", list(_TERM_OPTS.keys()))
            subject = st.text_input("Subject", placeholder="Mathematics")
            c4, c5 = st.columns(2)
            ca = c4.number_input("CA score", min_value=0.0, value=0.0, format="%.2f")
            exam = c5.number_input("Exam score", min_value=0.0, value=0.0,
                                   format="%.2f")
            teacher = st.selectbox("Teacher (optional)", ["—"] + list(teach_opts.keys()))
            remarks = st.text_input("Remarks (optional)")
            if st.form_submit_button("Save result", type="primary"):
                try:
                    with get_session() as s:
                        res = school_ops.record_result(
                            s, student_id=stu_opts[stu],
                            class_id=None if cls == "—" else cls_opts[cls],
                            academic_session_id=sess_opts[sess],
                            subject=subject, term_number=_TERM_OPTS[term_label],
                            ca_score=ca, exam_score=exam,
                            teacher_employee_id=(teach_opts.get(teacher)
                                                 if teacher != "—" else None),
                            remarks=remarks or None)
                        msg = f"Saved {res.subject}: {res.total} ({res.grade})"
                    ui.flash(msg); st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ---- Report card -----------------------------------------------------------
with tab_card:
    st.caption("A student's per-subject results and average for a term.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in s.execute(
            select(AcademicSession).order_by(AcademicSession.session_code)).scalars()}
        students = s.execute(select(Student).order_by(
            Student.last_name, Student.first_name)).scalars().all()
        stu_opts = {_student_label(st_): st_.id for st_ in students}
    if not (sess_opts and stu_opts):
        st.info("Add an academic session and enrol a student first.")
    else:
        c1, c2, c3 = st.columns(3)
        stu = c1.selectbox("Student", list(stu_opts.keys()), key="card_stu")
        sess = c2.selectbox("Session", list(sess_opts.keys()), key="card_sess")
        term_label = c3.selectbox("Term", list(_TERM_OPTS.keys()), key="card_term")
        with get_session() as s:
            card = school_ops.report_card(
                s, stu_opts[stu], sess_opts[sess], _TERM_OPTS[term_label])
        st.subheader(card["student"] or "—")
        ui.dataframe(pd.DataFrame(card["results"]), hide_index=True,
                     width="stretch")
        st.metric("Average", card["average"])


auth.render_logout_in_sidebar()
