"""School Attendance — mark daily attendance per class and view the summary.

Phase 4 of the school layer. Pure operational records: marking attendance does
NOT post to the GL. Pick a class and date, mark each student, and see the
present/absent/late/excused tally.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (AttendanceStatus, SchoolClass, Student,
                                  StudentStatus)
from bizclinik_erp.services import school_ops
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="School Attendance · Trakit365 ERP", layout="wide",
                   page_icon="🗓")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")
ui.hero("School Attendance", "Mark daily attendance · class summary",
         badge="AT", right_label="Module", right_value="School")

_STATUS_OPTS = ["PRESENT", "ABSENT", "LATE", "EXCUSED"]

tab_mark, tab_summary = st.tabs(["✅ Mark attendance", "📊 Summary"])


# ---- Mark attendance -------------------------------------------------------
with tab_mark:
    st.caption("Pick a class and date, set each student's status, then save. "
               "Nothing here posts to the ledger.")
    with get_session() as s:
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).where(SchoolClass.is_active == True)  # noqa: E712
            .order_by(SchoolClass.class_code)).scalars()}
    if not cls_opts:
        st.info("Add a class first (School Setup).")
    else:
        c1, c2 = st.columns(2)
        cls = c1.selectbox("Class", list(cls_opts.keys()))
        att_date = c2.date_input("Date", value=date.today())
        class_id = cls_opts[cls]
        with get_session() as s:
            students = s.execute(select(Student).where(
                Student.current_class_id == class_id,
                Student.status == StudentStatus.ACTIVE)
                .order_by(Student.last_name, Student.first_name)).scalars().all()
            roster = [{"id": st_.id,
                       "admission_no": st_.admission_no,
                       "name": f"{st_.first_name} {st_.last_name}"}
                      for st_ in students]
        if not roster:
            st.info("No active students in this class yet.")
        else:
            with st.form("attendance"):
                marks: dict[int, str] = {}
                for r in roster:
                    a, b = st.columns([3, 2])
                    a.markdown(f"**{r['name']}**  \n`{r['admission_no']}`")
                    marks[r["id"]] = b.selectbox(
                        "Status", _STATUS_OPTS, key=f"att_{r['id']}",
                        label_visibility="collapsed")
                if st.form_submit_button("Save attendance", type="primary"):
                    try:
                        with get_session() as s:
                            for sid, status in marks.items():
                                school_ops.record_attendance(
                                    s, student_id=sid, class_id=class_id,
                                    attendance_date=att_date,
                                    status=AttendanceStatus(status))
                        ui.flash(f"Saved attendance for {len(marks)} student(s)")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))


# ---- Summary ---------------------------------------------------------------
with tab_summary:
    st.caption("Daily tally of attendance marks for a class.")
    with get_session() as s:
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).order_by(SchoolClass.class_code)).scalars()}
    if not cls_opts:
        st.info("Add a class first (School Setup).")
    else:
        c1, c2 = st.columns(2)
        cls = c1.selectbox("Class", list(cls_opts.keys()), key="sum_cls")
        att_date = c2.date_input("Date", value=date.today(), key="sum_date")
        with get_session() as s:
            summ = school_ops.attendance_summary(s, cls_opts[cls], att_date)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Present", summ["present"])
        m2.metric("Absent", summ["absent"])
        m3.metric("Late", summ["late"])
        m4.metric("Excused", summ["excused"])
        m5.metric("Total", summ["total"])
        ui.dataframe(pd.DataFrame([summ]), hide_index=True, width="stretch")


auth.render_logout_in_sidebar()
