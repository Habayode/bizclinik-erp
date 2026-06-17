"""School Setup — academic calendar, classes, fee types and the fee grid.

Phase 0 of the school layer: pure master data (nothing posts to the GL). A fee
type is backed by a non-stockable product wired to an education income account,
so fee billing later flows through the normal sales/AR engine.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (AcademicSession, Account, AccountType,
                                  Employee, FeeType, SchoolClass,
                                  StudentFeeSchedule, Term)
from bizclinik_erp.services import school
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="School Setup · Trakit365 ERP", layout="wide",
                   page_icon="🏫")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")
ui.hero("School Setup", "Academic calendar · classes · fees",
         badge="SC", right_label="Module", right_value="School")

tab_sess, tab_term, tab_cls, tab_fee, tab_sched = st.tabs(
    ["📅 Sessions", "🗓️ Terms", "🏷️ Classes", "💰 Fee types", "🧮 Fee schedule"])

_TERM_OPTS = {"Annual / one-off": 0, "Term 1": 1, "Term 2": 2, "Term 3": 3}


def _sessions(s):
    return s.execute(select(AcademicSession).order_by(
        AcademicSession.session_code)).scalars().all()


# ---- Sessions --------------------------------------------------------------
with tab_sess:
    with get_session() as s:
        rows = [{"code": x.session_code, "name": x.name, "current": x.is_current,
                 "start": x.start_date, "end": x.end_date} for x in _sessions(s)]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.form("sess"):
        code = st.text_input("Session code", placeholder="2025/2026")
        c1, c2 = st.columns(2)
        sd = c1.date_input("Start date", value=None)
        ed = c2.date_input("End date", value=None)
        cur = st.checkbox("Set as the current session")
        if st.form_submit_button("Add session", type="primary"):
            try:
                with get_session() as s:
                    school.create_academic_session(s, session_code=code,
                                                   start_date=sd, end_date=ed,
                                                   make_current=cur)
                ui.flash(f"Added session {code}"); st.rerun()
            except ValueError as e:
                st.error(str(e))


# ---- Terms -----------------------------------------------------------------
with tab_term:
    with get_session() as s:
        sess_opts = {f"{x.session_code}": x.id for x in _sessions(s)}
        rows = [{"session": t.academic_session.session_code, "term": t.term_number,
                 "name": t.name, "start": t.start_date, "end": t.end_date}
                for t in s.execute(select(Term).order_by(
                    Term.academic_session_id, Term.term_number)).scalars()]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if not sess_opts:
        st.info("Add an academic session first.")
    else:
        with st.form("term"):
            sess = st.selectbox("Session", list(sess_opts.keys()))
            tn = st.selectbox("Term", [1, 2, 3])
            c1, c2 = st.columns(2)
            sd = c1.date_input("Start date", value=None, key="term_sd")
            ed = c2.date_input("End date", value=None, key="term_ed")
            if st.form_submit_button("Add term", type="primary"):
                try:
                    with get_session() as s:
                        school.create_term(s, academic_session_id=sess_opts[sess],
                                           term_number=int(tn), start_date=sd, end_date=ed)
                    ui.flash(f"Added Term {tn}"); st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ---- Classes ---------------------------------------------------------------
with tab_cls:
    with get_session() as s:
        rows = [{"code": c.class_code, "name": c.name, "level": c.form_level,
                 "arm": c.arm, "capacity": c.capacity,
                 "form tutor": (c.form_tutor.name if c.form_tutor else "")}
                for c in s.execute(select(SchoolClass).order_by(
                    SchoolClass.class_code)).scalars()]
        tutors = {f"{e.code} — {e.name}": e.id for e in s.execute(
            select(Employee).where(Employee.is_active == True)  # noqa: E712
            .order_by(Employee.name)).scalars()}
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.form("cls"):
        c1, c2 = st.columns(2)
        code = c1.text_input("Class code", placeholder="JSS1A")
        name = c2.text_input("Class name", placeholder="Junior Secondary 1A")
        c3, c4, c5 = st.columns(3)
        level = c3.number_input("Form level", min_value=0, value=0, step=1)
        arm = c4.text_input("Arm", placeholder="A")
        cap = c5.number_input("Capacity", min_value=0, value=0, step=1)
        tutor = st.selectbox("Form tutor (optional)", ["—"] + list(tutors.keys()))
        if st.form_submit_button("Add class", type="primary"):
            try:
                with get_session() as s:
                    school.create_school_class(
                        s, class_code=code, name=name,
                        form_level=int(level) or None, arm=arm or None,
                        capacity=int(cap) or None,
                        form_tutor_employee_id=tutors.get(tutor) if tutor != "—" else None)
                ui.flash(f"Added class {code}"); st.rerun()
            except ValueError as e:
                st.error(str(e))


# ---- Fee types -------------------------------------------------------------
with tab_fee:
    st.caption("A fee type is wired to an income account, so when you bill it "
               "the revenue lands in the right ledger account automatically. "
               "Fees are VAT-exempt.")
    with get_session() as s:
        rows = [{"code": f.code, "name": f.name, "mandatory": f.is_mandatory,
                 "income account": (f.product.income_account.code
                                    if f.product and f.product.income_account else "")}
                for f in s.execute(select(FeeType).order_by(FeeType.sort_order,
                                                            FeeType.code)).scalars()]
        income_opts = {f"{a.code} — {a.name}": a.code for a in s.execute(
            select(Account).where(Account.type == AccountType.INCOME,
                                  Account.is_postable == True)  # noqa: E712
            .order_by(Account.code)).scalars()}
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.form("fee"):
        c1, c2 = st.columns(2)
        code = c1.text_input("Fee code", placeholder="TUI")
        name = c2.text_input("Fee name", placeholder="Tuition")
        acct = st.selectbox("Income account", list(income_opts.keys()) or ["—"])
        mand = st.checkbox("Mandatory (billed to every student)", value=True)
        if st.form_submit_button("Add fee type", type="primary"):
            try:
                with get_session() as s:
                    school.create_fee_type(s, code=code, name=name,
                                          income_account_code=income_opts.get(acct, ""),
                                          is_mandatory=mand)
                ui.flash(f"Added fee type {code}"); st.rerun()
            except ValueError as e:
                st.error(str(e))


# ---- Fee schedule ----------------------------------------------------------
with tab_sched:
    st.caption("Set how much each class pays for a fee in a term. Use "
               "**Annual / one-off** for fees billed once per session, and "
               "leave the class as **All classes** for a school-wide fee.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in _sessions(s)}
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).order_by(SchoolClass.class_code)).scalars()}
        fee_opts = {f"{f.code} — {f.name}": f.id for f in s.execute(
            select(FeeType).order_by(FeeType.code)).scalars()}
        rows = [{"session": r.academic_session.session_code,
                 "class": (r.school_class.class_code if r.school_class else "ALL"),
                 "fee": r.fee_type.code,
                 "term": ("Annual" if r.term_number == 0 else f"T{r.term_number}"),
                 "amount": r.amount}
                for r in s.execute(select(StudentFeeSchedule).where(
                    StudentFeeSchedule.is_active == True)).scalars()]  # noqa: E712
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if not (sess_opts and fee_opts):
        st.info("Add a session and at least one fee type first.")
    else:
        with st.form("sched"):
            c1, c2 = st.columns(2)
            sess = c1.selectbox("Session", list(sess_opts.keys()))
            fee = c2.selectbox("Fee type", list(fee_opts.keys()))
            c3, c4, c5 = st.columns(3)
            cls = c3.selectbox("Class", ["All classes"] + list(cls_opts.keys()))
            term_label = c4.selectbox("Applies to", list(_TERM_OPTS.keys()))
            amount = c5.number_input("Amount (₦)", min_value=0.0, format="%.2f")
            if st.form_submit_button("Set fee amount", type="primary"):
                try:
                    with get_session() as s:
                        school.set_fee_schedule(
                            s, academic_session_id=sess_opts[sess],
                            fee_type_id=fee_opts[fee],
                            class_id=None if cls == "All classes" else cls_opts[cls],
                            term_number=_TERM_OPTS[term_label], amount=amount)
                    ui.flash("Fee amount set"); st.rerun()
                except ValueError as e:
                    st.error(str(e))


auth.render_logout_in_sidebar()
