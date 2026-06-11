"""Approvals — review the queue, approve/reject over-limit documents, and
(admin) set per-role authorisation limits."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import ApprovalStatus, User
from bizclinik_erp.services import approvals
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="Approvals · Trakit365 ERP", layout="wide",
                    page_icon="✅")
ui.inject_brand()
auth.require_login()
ui.hero("Approvals", "Authorisation limits & approval queue", badge="AP",
        right_label="Module", right_value="Controls")

_u = auth.current_user() or {}
UID, ROLE = _u.get("user_id"), _u.get("role")
IS_ADMIN = str(ROLE or "").upper() == "ADMIN"


def _usernames(s) -> dict:
    return {u.id: u.username for u in s.execute(select(User)).scalars()}


with get_session() as s:
    pend = approvals.list_pending(s)
    my_lim = approvals.role_limit(s, ROLE)
c1, c2, c3 = st.columns(3)
c1.metric("Pending approvals", len(pend))
c2.metric("Your role", str(ROLE or "—"))
c3.metric("Your limit", "Unlimited" if my_lim is None else f"₦{my_lim:,.0f}")

tab_queue, tab_mine, tab_hist, tab_limits = st.tabs(
    ["📥 Pending", "🙋 My requests", "🕘 History", "⚙️ Limits"])


# --------------------------------------------------------------------------- #
# Pending queue                                                               #
# --------------------------------------------------------------------------- #
with tab_queue:
    with get_session() as s:
        pend = approvals.list_pending(s)
        names = _usernames(s)
        rows = [{
            "id": r.id, "type": r.doc_type, "title": r.title,
            "amount": r.amount_ngn, "requested_by": names.get(r.requested_by_user_id, "—"),
            "role": r.requested_role or "—",
            "you can approve": approvals.can_approve(s, ROLE, r.amount_ngn)
            and r.requested_by_user_id != UID,
        } for r in pend]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("You can only approve amounts within your role limit, and not "
                   "your own requests.")
        cc1, cc2, cc3 = st.columns([1, 1, 2])
        rid = cc1.number_input("Request id", min_value=1, step=1, key="q_id")
        note = cc3.text_input("Note (for rejection)", key="q_note")
        if cc2.button("✅ Approve", type="primary", key="q_ok"):
            try:
                with get_session() as s:
                    out = approvals.approve(s, int(rid), approver_user_id=UID,
                                            approver_role=ROLE)
                st.success(f"Approved — {out['doc_type']} posted as {out['ref']}.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        if cc2.button("✋ Reject", key="q_no"):
            try:
                with get_session() as s:
                    approvals.reject(s, int(rid), approver_user_id=UID,
                                     approver_role=ROLE, note=note or None)
                st.warning(f"Request {int(rid)} rejected.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    else:
        st.caption("Nothing awaiting approval. 🎉")


# --------------------------------------------------------------------------- #
# My requests                                                                 #
# --------------------------------------------------------------------------- #
with tab_mine:
    with get_session() as s:
        mine = approvals.list_requests(s, requested_by=UID)
        rows = [{"id": r.id, "type": r.doc_type, "title": r.title,
                 "amount": r.amount_ngn, "status": r.status.value,
                 "result": r.result_ref or ""} for r in mine]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        cid = st.number_input("Cancel my pending request id", min_value=1, step=1,
                              key="mine_cancel")
        if st.button("Withdraw request", key="mine_btn"):
            try:
                with get_session() as s:
                    approvals.cancel(s, int(cid), user_id=UID)
                st.info(f"Request {int(cid)} withdrawn.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    else:
        st.caption("You haven't submitted any approval requests.")


# --------------------------------------------------------------------------- #
# History                                                                     #
# --------------------------------------------------------------------------- #
with tab_hist:
    with get_session() as s:
        names = _usernames(s)
        done = [r for r in approvals.list_requests(s)
                if r.status != ApprovalStatus.PENDING]
        rows = [{"id": r.id, "type": r.doc_type, "title": r.title,
                 "amount": r.amount_ngn, "status": r.status.value,
                 "decided_by": names.get(r.approver_user_id, "—"),
                 "result": r.result_ref or "",
                 "note": r.note or ""} for r in done]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("No decisions yet.")


# --------------------------------------------------------------------------- #
# Limits (admin)                                                              #
# --------------------------------------------------------------------------- #
with tab_limits:
    st.markdown("##### Per-role approval limits")
    st.caption("Documents (bills, purchase orders, payments) and payroll runs "
               "above a user's role limit are blocked and routed here for "
               "approval. Blank limit = unlimited.")
    with get_session() as s:
        lims = approvals.list_limits(s)
        rows = [{"role": l["role"],
                 "limit": ("Unlimited" if l["unlimited"]
                           else f"₦{l['limit_ngn']:,.0f}")}
                for l in lims]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    if IS_ADMIN:
        st.markdown("##### Update a limit")
        with st.form("set_limit"):
            lc1, lc2, lc3 = st.columns([1, 1, 1])
            role = lc1.selectbox("Role", [l["role"] for l in lims])
            unlimited = lc2.checkbox("Unlimited", value=False)
            amount = lc3.number_input("Limit (₦)", min_value=0.0, step=50000.0,
                                      disabled=unlimited)
            if st.form_submit_button("Save limit", type="primary"):
                with get_session() as s:
                    approvals.set_limit(s, role, None if unlimited else float(amount))
                st.success(f"Updated {role} limit.")
                st.rerun()
    else:
        st.info("Only an Admin can change approval limits.")

auth.render_logout_in_sidebar()
