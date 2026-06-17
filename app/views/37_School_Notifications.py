"""Parent notifications — fee reminders & statements by SMS/email.

SMS uses the provider-agnostic gateway (default: log/demo mode — messages are
recorded, not transmitted, until a real gateway is configured). Email reuses the
ERP's SMTP settings. Every send is recorded in the notification log.
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
from bizclinik_erp.models import Student, StudentStatus
from bizclinik_erp.services import school_notify, school_billing, sms
from bizclinik_erp.services import notifications as _email
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Parent Notifications · Trakit365 ERP", layout="wide",
                   page_icon="📣")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")
ui.hero("Parent Notifications", "Fee reminders · statements · SMS / email",
         badge="PN", right_label="Module", right_value="School")

# --- channel readiness banner ----------------------------------------------
_sms_name = sms.get_sms_provider().name
if _sms_name == "log":
    st.warning("SMS is in **log/demo mode** — reminders are recorded but not "
               "actually sent. Set `SMS_PROVIDER=termii` (or `twilio`) + the "
               "gateway credentials to send real SMS.")
else:
    st.success(f"SMS gateway: **{_sms_name}** (live).")
st.caption(("Email: SMTP is configured ✓" if _email.smtp_configured()
            else "Email: SMTP not configured — email sends will fail until "
                 "SMTP_HOST/USER/PASS/FROM are set."))

tab_remind, tab_stmt, tab_log = st.tabs(
    ["🔔 Fee reminders", "📃 Statements", "📜 Log"])


def _student_opts(s):
    return {f"{st_.admission_no} — {st_.first_name} {st_.last_name}": st_.id
            for st_ in s.execute(select(Student).where(
                Student.status == StudentStatus.ACTIVE).order_by(
                Student.admission_no)).scalars()}


# ---- Fee reminders ---------------------------------------------------------
with tab_remind:
    channel = st.radio("Channel", ["SMS", "EMAIL"], horizontal=True)
    audience = st.radio("Send to", ["All defaulters", "One student"], horizontal=True)
    if audience == "One student":
        with get_session() as s:
            opts = _student_opts(s)
        if not opts:
            st.info("No active students yet.")
        else:
            sel = st.selectbox("Student", list(opts.keys()))
            if st.button("Send reminder", type="primary"):
                with get_session() as s:
                    n = school_notify.send_fee_reminder(s, student_id=opts[sel], channel=channel)
                if n is None:
                    st.info("That student has no outstanding balance — nothing to send.")
                else:
                    ui.flash(f"Reminder {n.status.value.lower()} to {n.recipient or 'n/a'}.")
                    st.rerun()
    else:
        st.caption("Sends a fee reminder to every active student with an "
                   "outstanding balance.")
        if st.button("Send to all defaulters", type="primary"):
            with get_session() as s:
                tally = school_notify.bulk_fee_reminders(s, channel=channel)
            ui.flash(f"Done — sent {tally['sent']}, logged {tally['logged']}, "
                     f"failed {tally['failed']}, skipped {tally['skipped']}.")
            st.rerun()


# ---- Statements ------------------------------------------------------------
with tab_stmt:
    st.caption("Email a student's fee statement (PDF) to the guardian on file. "
               "Requires SMTP configured.")
    with get_session() as s:
        opts = _student_opts(s)
    if not opts:
        st.info("No active students yet.")
    else:
        sel = st.selectbox("Student", list(opts.keys()), key="stmt_student")
        c1, c2 = st.columns(2)
        ps = c1.date_input("Period start", value=date(date.today().year, 1, 1))
        pe = c2.date_input("Period end", value=date.today())
        if st.button("Email statement", type="primary"):
            with get_session() as s:
                n = school_notify.send_statement_email(
                    s, student_id=opts[sel], period_start=ps, period_end=pe)
            if n.status.value == "SENT":
                ui.flash(f"Statement emailed to {n.recipient}.")
            else:
                st.error(f"Not sent: {n.error or 'unknown reason'}")
            st.rerun()


# ---- Log -------------------------------------------------------------------
with tab_log:
    with get_session() as s:
        rows = [{"when": str(n.created_at)[:19], "student": n.student_id,
                 "channel": n.channel.value, "kind": n.kind.value,
                 "to": n.recipient, "status": n.status.value,
                 "provider": n.provider, "error": n.error}
                for n in school_notify.list_notifications(s, limit=300)]
    if rows:
        ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("No notifications sent yet.")


auth.render_logout_in_sidebar()
