"""Recruitment — job openings, candidates, and the application pipeline (HR)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp.models import ApplicationStage, OpeningStatus
from bizclinik_erp.services import hr
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="Recruitment · BizClinik ERP", layout="wide",
                    page_icon="🧲")
ui.inject_brand()
auth.require_login()
ui.hero("Recruitment", "Openings · candidates · pipeline", badge="RC",
        right_label="Module", right_value="HR")

uid = auth.current_user_id()

with get_session() as s:
    rep = hr.recruitment_summary(s)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Open openings", rep["open_openings"])
c2.metric("Candidates", rep["candidates"])
c3.metric("In pipeline", rep["in_pipeline"])
c4.metric("Hired", rep["hired"])

tab_open, tab_cand, tab_pipe = st.tabs(
    ["📋 Openings", "👤 Candidates", "🔀 Pipeline"])


# --------------------------------------------------------------------------- #
# Openings                                                                     #
# --------------------------------------------------------------------------- #
with tab_open:
    with get_session() as s:
        ops = hr.list_openings(s)
        orows = [{"id": o.id, "title": o.title, "department": o.department or "",
                  "location": o.location or "", "type": o.employment_type or "",
                  "headcount": o.headcount, "status": o.status.value} for o in ops]
    if orows:
        st.dataframe(pd.DataFrame(orows), hide_index=True, width="stretch")
        cc1, cc2 = st.columns(2)
        op_id = cc1.number_input("Opening id", min_value=1, step=1, key="op_id")
        new_status = cc2.selectbox("Set status", [s.value for s in OpeningStatus],
                                   key="op_status")
        if st.button("Update status", key="op_btn"):
            with get_session() as s:
                hr.set_opening_status(s, int(op_id), OpeningStatus(new_status))
            st.success(f"Opening {int(op_id)} → {new_status}"); st.rerun()
    else:
        st.caption("No openings yet — create one below.")

    with st.expander("➕ New opening"):
        with st.form("new_opening"):
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("Title *")
            dept = c2.text_input("Department")
            loc = c3.text_input("Location")
            c4, c5 = st.columns(2)
            etype = c4.selectbox("Employment type",
                                 ["full-time", "part-time", "contract", "intern"])
            hc = c5.number_input("Headcount", min_value=1, step=1, value=1)
            desc = st.text_area("Description")
            if st.form_submit_button("Create opening", type="primary") and title:
                with get_session() as s:
                    hr.create_opening(s, title=title, department=dept or None,
                                      location=loc or None, employment_type=etype,
                                      headcount=int(hc), description=desc or None,
                                      owner_user_id=uid)
                st.success("Opening created."); st.rerun()


# --------------------------------------------------------------------------- #
# Candidates                                                                   #
# --------------------------------------------------------------------------- #
with tab_cand:
    with st.form("new_candidate"):
        st.markdown("##### Add a candidate")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Name *")
        email = c2.text_input("Email")
        phone = c3.text_input("Phone")
        c4, c5 = st.columns(2)
        source = c4.text_input("Source", placeholder="referral / job board / agency")
        resume = c5.text_input("Resume link")
        if st.form_submit_button("Add candidate", type="primary"):
            if not name.strip():
                st.error("Name is required.")
            else:
                with get_session() as s:
                    hr.add_candidate(s, name=name, email=email or None,
                                     phone=phone or None, source=source or None,
                                     resume_url=resume or None)
                st.success("Candidate added."); st.rerun()

    st.divider()
    with get_session() as s:
        cands = hr.list_candidates(s)
        crows = [{"id": c.id, "name": c.name, "email": c.email or "",
                  "phone": c.phone or "", "source": c.source or ""} for c in cands]
    if crows:
        st.dataframe(pd.DataFrame(crows), hide_index=True, width="stretch")
        st.markdown("##### File an application")
        with get_session() as s:
            ops = hr.list_openings(s, open_only=True)
            op_opts = {f"{o.title} (id {o.id})": o.id for o in ops}
        if op_opts:
            ac1, ac2 = st.columns(2)
            cand_id = ac1.number_input("Candidate id", min_value=1, step=1, key="ap_cand")
            op_label = ac2.selectbox("Opening", list(op_opts.keys()), key="ap_open")
            if st.button("Apply to opening", key="ap_btn"):
                with get_session() as s:
                    hr.apply(s, opening_id=op_opts[op_label], candidate_id=int(cand_id))
                st.success("Application filed."); st.rerun()
        else:
            st.caption("No open openings to apply to — open one first.")
    else:
        st.caption("No candidates yet.")


# --------------------------------------------------------------------------- #
# Pipeline                                                                     #
# --------------------------------------------------------------------------- #
with tab_pipe:
    st.markdown("##### Applications")
    with get_session() as s:
        apps = hr.list_applications(s)
        cands = {c.id: c.name for c in hr.list_candidates(s)}
        ops = {o.id: o.title for o in hr.list_openings(s)}
        arows = [{"id": a.id, "candidate": cands.get(a.candidate_id, "?"),
                  "opening": ops.get(a.opening_id, "?"), "stage": a.stage.value,
                  "applied": a.applied_date,
                  "hired_emp_id": a.employee_id or ""} for a in apps]
    if arows:
        st.dataframe(pd.DataFrame(arows), hide_index=True, width="stretch")
        st.markdown("##### Move a stage")
        mc1, mc2 = st.columns(2)
        app_id = mc1.number_input("Application id", min_value=1, step=1, key="mv_app")
        stage = mc2.selectbox("Stage", [s.value for s in ApplicationStage], key="mv_stage")
        if st.button("Update stage", key="mv_app_btn"):
            with get_session() as s:
                hr.move_application(s, int(app_id), ApplicationStage(stage))
            st.success(f"Application {int(app_id)} → {stage}"); st.rerun()

        st.divider()
        st.markdown("##### Hire a candidate")
        st.caption("Creates an Employee from the candidate, marks the application "
                   "HIRED and fills the opening. Payroll takes over from there.")
        with st.form("hire"):
            h1, h2, h3 = st.columns(3)
            h_app = h1.number_input("Application id", min_value=1, step=1, key="hire_app")
            h_gross = h2.number_input("Monthly gross (₦)", min_value=0.0, step=10000.0)
            h_paye = h3.number_input("PAYE rate", min_value=0.0, max_value=1.0, step=0.01)
            if st.form_submit_button("Hire", type="primary"):
                with get_session() as s:
                    res = hr.hire_candidate(s, int(h_app), monthly_gross=h_gross,
                                            paye_rate=h_paye)
                if res.get("already_hired"):
                    st.info(f"Already hired → employee #{res['employee_id']}.")
                else:
                    st.success(f"Hired → employee #{res['employee_id']}. "
                               "See the Employees & Payroll pages.")
                st.rerun()
    else:
        st.caption("No applications yet.")

auth.render_logout_in_sidebar()
