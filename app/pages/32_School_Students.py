"""School Students — the roll: directory of students and enrolment.

Phase 1 of the school layer. Enrolling a student creates their billing Customer
plus an append-only enrolment row; nothing posts to the GL here (fees are billed
later through the normal sales engine against the student's Customer).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (AcademicSession, SchoolClass, Student,
                                  StudentStatus)
from bizclinik_erp.services import school_enrol
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="School Students · Trakit365 ERP", layout="wide",
                   page_icon="🎓")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")
ui.hero("School Students", "The roll · directory · enrolment",
         badge="ST", right_label="Module", right_value="School")

tab_dir, tab_enrol, tab_bulk = st.tabs(
    ["📋 Directory", "🎓 Enrol", "📥 Bulk import"])


# ---- Directory -------------------------------------------------------------
with tab_dir:
    with get_session() as s:
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).order_by(SchoolClass.class_code)).scalars()}
    flt = st.selectbox("Filter by class", ["All classes"] + list(cls_opts.keys()))
    class_id = None if flt == "All classes" else cls_opts[flt]
    with get_session() as s:
        students = school_enrol.list_students(s, class_id=class_id)
        rows = [{"admission_no": st_.admission_no,
                 "name": f"{st_.first_name} {st_.last_name}",
                 "class": (st_.current_class.class_code if st_.current_class else ""),
                 "status": st_.status.value,
                 "guardian": st_.guardian_name or "",
                 "phone": st_.guardian_phone or ""}
                for st_ in students]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---- Enrol -----------------------------------------------------------------
with tab_enrol:
    st.caption("Enrolling creates the student's billing Customer and an "
               "enrolment record. Leave the admission number blank to "
               "auto-generate the next STU-#### number.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in s.execute(
            select(AcademicSession).where(AcademicSession.is_active == True)  # noqa: E712
            .order_by(AcademicSession.session_code)).scalars()}
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).where(SchoolClass.is_active == True)  # noqa: E712
            .order_by(SchoolClass.class_code)).scalars()}
    if not (sess_opts and cls_opts):
        st.info("Add an academic session and at least one class first "
                "(School Setup).")
    else:
        with st.form("enrol"):
            c1, c2 = st.columns(2)
            first = c1.text_input("First name")
            last = c2.text_input("Last name")
            c3, c4 = st.columns(2)
            sess = c3.selectbox("Academic session", list(sess_opts.keys()))
            cls = c4.selectbox("Class", list(cls_opts.keys()))
            c5, c6 = st.columns(2)
            adm = c5.text_input("Admission no (optional)", placeholder="auto")
            gender = c6.selectbox("Gender", ["—", "Male", "Female"])
            c7, c8 = st.columns(2)
            dob = c7.date_input("Date of birth", value=None)
            admitted = c8.date_input("Date admitted", value=None)
            gname = st.text_input("Guardian name")
            c9, c10 = st.columns(2)
            gphone = c9.text_input("Guardian phone")
            gemail = c10.text_input("Guardian email")
            if st.form_submit_button("Enrol student", type="primary"):
                try:
                    with get_session() as s:
                        st_ = school_enrol.enrol_student(
                            s, first_name=first, last_name=last,
                            class_id=cls_opts[cls],
                            academic_session_id=sess_opts[sess],
                            admission_no=adm or None,
                            guardian_name=gname or None,
                            guardian_phone=gphone or None,
                            guardian_email=gemail or None,
                            dob=dob, gender=None if gender == "—" else gender,
                            date_admitted=admitted)
                        msg = f"Enrolled {st_.first_name} {st_.last_name} ({st_.admission_no})"
                    ui.flash(msg); st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ---- Bulk import -----------------------------------------------------------
with tab_bulk:
    st.caption("Enrol a whole roster at once. Download the template, fill one "
               "row per student, pick the session, and upload — each row creates "
               "the student, their class enrolment **and** billing record. "
               "Class codes must already exist in **School Setup → Classes**.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in s.execute(
            select(AcademicSession).where(AcademicSession.is_active == True)  # noqa: E712
            .order_by(AcademicSession.session_code)).scalars()}
        cur = s.execute(select(AcademicSession).where(
            AcademicSession.is_current == True)).scalars().first()  # noqa: E712
    if not sess_opts:
        st.info("Add an academic session first (School Setup → Sessions).")
    else:
        keys = list(sess_opts.keys())
        idx = keys.index(cur.session_code) if cur and cur.session_code in keys else 0
        bsess = st.selectbox("Enrol into session", keys, index=idx, key="bulk_sess")
        st.download_button(
            "⬇ Download student template (.xlsx)",
            data=school_enrol.student_template_bytes(),
            file_name="Trakit365_students_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="stu_tpl")
        up = st.file_uploader("Upload your filled roster", type=["xlsx"],
                              key="stu_upload")
        if up is not None:
            try:
                df_up = pd.read_excel(up)
            except Exception as e:   # noqa: BLE001
                st.error(f"Couldn't read that file: {e}")
                df_up = None
            if df_up is not None:
                st.caption("Preview:")
                st.dataframe(df_up.head(30), hide_index=True, width="stretch")
                if st.button("Enrol all", type="primary", key="stu_import"):
                    try:
                        with get_session() as s:
                            res = school_enrol.import_students(
                                s, df_up, academic_session_id=sess_opts[bsess])
                        if res["errors"]:
                            st.success(f"Enrolled {res['created']}; "
                                       f"{res['skipped']} skipped.")
                            st.warning("These rows were skipped — fix and "
                                       "re-upload just those:")
                            st.dataframe(pd.DataFrame({"issue": res["errors"]}),
                                         hide_index=True, width="stretch")
                        else:
                            ui.flash(f"Enrolled {res['created']} student(s).")
                            st.rerun()
                    except ValueError as e:
                        st.error(str(e))


auth.render_logout_in_sidebar()
