"""School Dashboard — the school-first landing page.

At-a-glance enrolment, fee collection and staffing for the current session.
Read-only; all figures derive from the school + accounting data.
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
from bizclinik_erp.models import AcademicSession, Company
from bizclinik_erp.services import school_staff
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="School Dashboard · Trakit365 ERP", layout="wide",
                   page_icon="🏫")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")

with get_session() as s:
    co = s.query(Company).first()
    school_name = (co.name if co and co.name else "School")
    cur = s.execute(select(AcademicSession).where(
        AcademicSession.is_current == True)).scalars().first()  # noqa: E712
    cur_label = cur.session_code if cur else "no current session set"
    cur_id = cur.id if cur else None
    dash = school_staff.school_dashboard(s, academic_session_id=cur_id)

ui.hero(school_name, f"School dashboard · session {cur_label}",
         badge="🏫", right_label="Module", right_value="School")

if not cur:
    st.info("No current academic session yet. Go to **School Setup → Sessions** "
            "to create one and mark it current, then add classes, fee types and "
            "the fee grid.")

# --- KPI cards --------------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Students enrolled", dash.get("total_students", 0))
c2.metric("Teaching & staff", dash.get("total_teachers", 0))
c3.metric("Fee defaulters", dash.get("defaulter_count", 0))

c4, c5, c6 = st.columns(3)
c4.metric("Fees billed", f"₦{dash.get('fees_billed', 0):,.2f}")
c5.metric("Fees collected", f"₦{dash.get('fees_collected', 0):,.2f}")
c6.metric("Outstanding", f"₦{dash.get('fees_outstanding', 0):,.2f}")

billed = dash.get("fees_billed", 0) or 0
if billed:
    pct = (dash.get("fees_collected", 0) or 0) / billed
    st.progress(min(max(pct, 0.0), 1.0), text=f"{pct * 100:.0f}% of billed fees collected")

st.divider()

# --- Enrolment by class -----------------------------------------------------
st.subheader("Enrolment by class")
rows = dash.get("enrolment_by_class") or []
if rows:
    df = pd.DataFrame(rows).rename(columns={"class_code": "Class", "count": "Students"})
    cc1, cc2 = st.columns([2, 3])
    cc1.dataframe(df, hide_index=True, width="stretch")
    try:
        cc2.bar_chart(df.set_index("Class"))
    except Exception:   # noqa: BLE001
        pass
else:
    st.caption("No students enrolled yet — add them under **School → Students**.")

st.caption("Bill a term from **School → School Fees**, record payments there, and "
           "send reminders to defaulters from **School → Parent Notifications**.")

auth.render_logout_in_sidebar()
