"""CRM — leads, deal pipeline, and follow-up activities."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (
    ActivityKind, Customer, DealStage, LeadStatus,
)
from bizclinik_erp.services import crm
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="CRM · BizClinik ERP", layout="wide", page_icon="🤝")
ui.inject_brand()
auth.require_login()
from bizclinik_erp import gate as _gate; _gate.require_feature("crm", "CRM")
ui.hero("CRM", "Leads · pipeline · follow-ups", badge="CR",
        right_label="Module", right_value="Sales")

uid = auth.current_user_id()
tab_pipe, tab_leads, tab_acts = st.tabs(
    ["📊 Pipeline", "👤 Leads", "🔔 Follow-ups"])


# --------------------------------------------------------------------------- #
# Pipeline                                                                     #
# --------------------------------------------------------------------------- #
with tab_pipe:
    with get_session() as s:
        rep = crm.pipeline_summary(s)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open pipeline", f"₦{rep['open_value']:,.0f}")
    c2.metric("Open deals", rep["open_count"])
    c3.metric("Won value", f"₦{rep['won_value']:,.0f}")
    c4.metric("Win rate", f"{rep['win_rate']*100:.0f}%")

    st.markdown("##### By stage")
    stage_rows = [{"stage": k, "count": v["count"], "value (₦)": v["value"]}
                  for k, v in rep["by_stage"].items()]
    st.dataframe(pd.DataFrame(stage_rows), hide_index=True, width="stretch")

    st.divider()
    st.markdown("##### Open deals")
    with get_session() as s:
        deals = crm.list_deals(s, open_only=True)
        drows = [{"id": d.id, "title": d.title, "stage": d.stage.value,
                  "amount": d.amount, "expected close": d.expected_close}
                 for d in deals]
    if drows:
        st.dataframe(pd.DataFrame(drows), hide_index=True, width="stretch")
        cm1, cm2 = st.columns(2)
        move_id = cm1.number_input("Deal id", min_value=1, step=1, key="mv_id")
        new_stage = cm2.selectbox("Move to stage", [s.value for s in DealStage],
                                  key="mv_stage")
        if st.button("Update stage", key="mv_btn"):
            with get_session() as s:
                crm.move_stage(s, int(move_id), DealStage(new_stage))
            st.success(f"Deal {int(move_id)} → {new_stage}")
            st.rerun()
    else:
        st.caption("No open deals. Create one below or convert a lead.")

    with st.expander("➕ New deal"):
        with st.form("new_deal"):
            t = st.text_input("Title")
            a = st.number_input("Amount (₦)", min_value=0.0, step=1000.0)
            stg = st.selectbox("Stage", [s.value for s in DealStage], index=0)
            ec = st.date_input("Expected close", value=None)
            if st.form_submit_button("Create deal", type="primary") and t:
                with get_session() as s:
                    crm.create_deal(s, title=t, amount=a, stage=DealStage(stg),
                                    expected_close=ec, owner_user_id=uid)
                st.success("Deal created."); st.rerun()


# --------------------------------------------------------------------------- #
# Leads                                                                        #
# --------------------------------------------------------------------------- #
with tab_leads:
    with st.form("new_lead"):
        st.markdown("##### Capture a lead")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Name *")
        company = c2.text_input("Company")
        source = c3.text_input("Source", placeholder="referral / web / ad")
        c4, c5 = st.columns(2)
        email = c4.text_input("Email")
        phone = c5.text_input("Phone")
        if st.form_submit_button("Add lead", type="primary"):
            if not name.strip():
                st.error("Name is required.")
            else:
                with get_session() as s:
                    crm.create_lead(s, name=name, company=company, email=email,
                                    phone=phone, source=source, owner_user_id=uid)
                st.success("Lead added."); st.rerun()

    st.divider()
    with get_session() as s:
        leads = crm.list_leads(s)
        lrows = [{"id": l.id, "name": l.name, "company": l.company or "",
                  "email": l.email or "", "status": l.status.value,
                  "source": l.source or ""} for l in leads]
    if lrows:
        st.dataframe(pd.DataFrame(lrows), hide_index=True, width="stretch")
        st.markdown("##### Convert a lead → customer")
        cc1, cc2, cc3 = st.columns([1, 1, 1])
        conv_id = cc1.number_input("Lead id", min_value=1, step=1, key="cv_id")
        mk_deal = cc2.checkbox("Also open a deal", value=True)
        deal_amt = cc3.number_input("Deal amount (₦)", min_value=0.0, step=1000.0)
        if st.button("Convert", key="cv_btn"):
            with get_session() as s:
                res = crm.convert_lead(s, int(conv_id), create_deal=mk_deal,
                                       deal_amount=deal_amt)
            st.success(f"Converted → customer #{res['customer_id']}"
                       + (f", deal #{res['deal_id']}" if res['deal_id'] else ""))
            st.rerun()
    else:
        st.caption("No leads yet — capture one above.")


# --------------------------------------------------------------------------- #
# Follow-ups                                                                   #
# --------------------------------------------------------------------------- #
with tab_acts:
    with get_session() as s:
        due = crm.followups_due(s)
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Overdue", due["overdue"])
    d2.metric("Due today", due["today"])
    d3.metric("Upcoming", due["upcoming"])
    d4.metric("No date", due["undated"])

    with st.expander("➕ Log a follow-up", expanded=not any(due.values())):
        with st.form("new_act"):
            subj = st.text_input("Subject")
            c1, c2 = st.columns(2)
            kind = c1.selectbox("Type", [k.value for k in ActivityKind])
            dd = c2.date_input("Due date", value=date.today())
            if st.form_submit_button("Add follow-up", type="primary") and subj:
                with get_session() as s:
                    crm.log_activity(s, subject=subj, kind=ActivityKind(kind),
                                     due_date=dd, owner_user_id=uid)
                st.success("Follow-up logged."); st.rerun()

    st.divider()
    with get_session() as s:
        acts = crm.list_activities(s, open_only=True)
        arows = [{"id": a.id, "subject": a.subject, "type": a.kind.value,
                  "due": a.due_date} for a in acts]
    if arows:
        st.dataframe(pd.DataFrame(arows), hide_index=True, width="stretch")
        done_id = st.number_input("Mark done — activity id", min_value=1, step=1,
                                  key="done_id")
        if st.button("Mark done", key="done_btn"):
            with get_session() as s:
                crm.complete_activity(s, int(done_id))
            st.success(f"Activity {int(done_id)} completed."); st.rerun()
    else:
        st.caption("No open follow-ups. 🎉")


auth.render_logout_in_sidebar()
