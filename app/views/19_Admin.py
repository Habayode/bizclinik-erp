"""Admin page — users, periods, audit log."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select, desc

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (
    AuditLog,
    FiscalPeriod,
    PeriodStatus,
    Role,
    User,
)
from bizclinik_erp.services import fiscal as fiscal_svc
from bizclinik_erp.services import users as user_svc
from bizclinik_erp.services.audit import list_recent
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui


st.set_page_config(page_title="Admin · Trakit365 ERP", layout="wide",
                    page_icon="🛡️")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.users",
                   error="Admins only — sign in with an admin account.")
ui.hero("Admin", "Users · Periods · Audit log",
         badge="AD", right_label="Module", right_value="Governance")


tab_users, tab_periods, tab_audit = st.tabs(
    ["👤 Users", "📅 Fiscal periods", "📜 Audit log"]
)


# ---- Users ---------------------------------------------------------------

with tab_users:
    st.subheader("All users")
    with get_session() as s:
        users = user_svc.list_users(s, include_inactive=True)
        rows = [{
            "id": u.id, "username": u.username, "email": u.email or "",
            "full_name": u.full_name or "", "role": u.role.value,
            "active": u.is_active,
            "last_login": u.last_login_at.isoformat(" ", "minutes") if u.last_login_at else "",
            "failed_logins": u.failed_login_count,
        } for u in users]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Add user")
    with st.form("new_user"):
        c1, c2 = st.columns(2)
        username = c1.text_input("Username", help="3-32 chars, lowercase preferred")
        full_name = c2.text_input("Full name")
        email = c1.text_input("Email")
        role = c2.selectbox("Role", [r.value for r in Role])
        pw = c1.text_input("Initial password", type="password")
        must_change = c2.checkbox("Force password change on first login", value=True)
        submit = st.form_submit_button("Create user", type="primary")
    # Plan gate: cap active users to the tenant plan's max_users.
    from bizclinik_erp.services import billing as _billing
    _tenant = auth.active_tenant()
    _limit = _billing.user_limit(_tenant)
    with get_session() as s:
        _active_count = len(user_svc.list_users(s, include_inactive=False))
    if _limit is not None and _active_count >= _limit:
        st.warning(
            f"🔒 Your **{_billing.effective_plan(_tenant).name}** plan allows up "
            f"to **{_limit}** active users (you have {_active_count}). Upgrade on "
            "the **Billing** page to add more.",
            icon="🔒",
        )

    if submit:
        if _limit is not None and _active_count >= _limit:
            st.error(
                f"User limit reached ({_active_count}/{_limit}). Upgrade your "
                "plan to add more users.")
        else:
            try:
                with get_session() as s:
                    u = user_svc.create_user(
                        s, username=username, password=pw, role=role,
                        email=email or None, full_name=full_name or None,
                        must_change_password=must_change,
                        created_by_user_id=auth.current_user_id(),
                    )
                    st.success(f"Created {u.username} ({u.role.value})")
            except ValueError as e:
                st.error(str(e))

    st.divider()
    st.subheader("Change role / deactivate")
    with get_session() as s:
        users = user_svc.list_users(s, include_inactive=True)
        opts = {f"{u.username} ({u.role.value})": u.id for u in users}
    if opts:
        with st.form("change_role"):
            sel = st.selectbox("User", list(opts.keys()))
            new_role = st.selectbox("New role", [r.value for r in Role], key="cr_role")
            deactivate = st.checkbox("Deactivate this user instead")
            new_pw = st.text_input("Reset password to (leave blank to skip)", type="password")
            submit = st.form_submit_button("Apply", type="primary")
        if submit:
            with get_session() as s:
                if deactivate:
                    user_svc.deactivate(s, opts[sel],
                                          acting_user_id=auth.current_user_id())
                    st.warning(f"Deactivated {sel}")
                else:
                    user_svc.set_role(s, opts[sel], new_role,
                                        acting_user_id=auth.current_user_id())
                    if new_pw:
                        user_svc.set_password(s, opts[sel], new_pw,
                                                acting_user_id=auth.current_user_id())
                    st.success(f"Updated {sel} → {new_role}")


# ---- Fiscal periods -------------------------------------------------------

with tab_periods:
    st.subheader("Periods")
    c1, c2 = st.columns(2)
    year = c1.number_input("Year", min_value=2000, max_value=2100, value=date.today().year, step=1)
    with get_session() as s:
        periods = fiscal_svc.list_periods(s, year=int(year))
        rows = [{
            "year": p.year, "month": p.month, "status": p.status.value,
            "period_start": p.period_start, "period_end": p.period_end,
            "closed_at": p.closed_at.isoformat(" ", "minutes") if p.closed_at else "",
            "notes": p.notes or "",
        } for p in periods]
    if rows:
        ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("No periods registered for this year yet — they're created on first JE posting.")

    st.divider()
    st.subheader("Close a period")
    with st.form("close_period"):
        c1, c2, c3 = st.columns(3)
        cy = c1.number_input("Year", min_value=2000, max_value=2100,
                              value=date.today().year, step=1, key="cy")
        cm = c2.selectbox("Month", list(range(1, 13)),
                           index=date.today().month - 1, key="cm")
        notes = c3.text_input("Notes (optional)")
        submit = st.form_submit_button("Close period", type="primary")
    if submit:
        try:
            with get_session() as s:
                p = fiscal_svc.close_period(s, int(cy), int(cm),
                                              user_id=auth.current_user_id(),
                                              notes=notes or None)
                st.success(f"Closed {p.year}-{p.month:02d}")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("Reopen a period (admin override)")
    with st.form("reopen_period"):
        c1, c2, c3 = st.columns(3)
        ry = c1.number_input("Year", min_value=2000, max_value=2100,
                              value=date.today().year, step=1, key="ry")
        rm = c2.selectbox("Month", list(range(1, 13)),
                           index=date.today().month - 1, key="rm")
        reason = c3.text_input("Reason (required, ≥5 chars)")
        submit = st.form_submit_button("Reopen", type="secondary")
    if submit:
        try:
            with get_session() as s:
                p = fiscal_svc.reopen_period(s, int(ry), int(rm),
                                               user_id=auth.current_user_id(),
                                               reason=reason)
                st.warning(f"Reopened {p.year}-{p.month:02d}")
        except Exception as e:
            st.error(str(e))


# ---- Audit log -----------------------------------------------------------

with tab_audit:
    st.subheader("Recent activity")
    c1, c2, c3 = st.columns(3)
    limit = c1.number_input("Limit", min_value=20, max_value=1000, value=200, step=20)
    filter_user = c2.text_input("Filter by username (optional)")
    filter_action = c3.text_input("Filter by action (e.g. POST, VOID)")
    with get_session() as s:
        q = select(AuditLog).order_by(desc(AuditLog.ts))
        if filter_user:
            q = q.where(AuditLog.username == filter_user.strip().lower())
        if filter_action:
            q = q.where(AuditLog.action == filter_action.strip().upper())
        q = q.limit(int(limit))
        logs = list(s.execute(q).scalars())
        rows = [{
            "ts": l.ts.isoformat(" ", "seconds"),
            "user": l.username or "",
            "action": l.action.value,
            "entity": f"{l.entity_type or ''} #{l.entity_id or ''}",
            "description": l.description or "",
            "source": l.source or "",
        } for l in logs]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=600)


auth.render_logout_in_sidebar()
