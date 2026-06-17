"""School Fees — bill students through the normal sales/AR engine.

Phase 2 of the school layer: the first GL impact. Billing builds fee lines from
the Phase 0 fee grid and raises real SalesInvoices via ``sales.issue_invoice``,
so revenue lands in each fee's education income account — no parallel ledger.
Billing is idempotent per (student, session, term), so a class run can be re-run
safely without double-invoicing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (AcademicSession, BankAccount, SchoolClass,
                                  StudentFeeBilling)
from bizclinik_erp.services import school_billing
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="School Fees · Trakit365 ERP", layout="wide",
                   page_icon="💰")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.school")
ui.hero("School Fees", "Bill fees · sales/AR engine",
         badge="FE", right_label="Module", right_value="School")

tab_bulk, tab_pay, tab_status, tab_log = st.tabs(
    ["💰 Bulk issue", "💵 Record payment", "📊 Fee status / defaulters",
     "📋 Billing log"])

_TERM_OPTS = {"Term 1": 1, "Term 2": 2, "Term 3": 3, "Annual / one-off": 0}


# ---- Bulk issue ------------------------------------------------------------
with tab_bulk:
    st.caption("Bill an entire class for a term. Each student's fee grid is "
               "raised as a SalesInvoice; students already billed for the term "
               "are skipped, so re-running is safe.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in s.execute(
            select(AcademicSession).where(AcademicSession.is_active == True)  # noqa: E712
            .order_by(AcademicSession.session_code)).scalars()}
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).where(SchoolClass.is_active == True)  # noqa: E712
            .order_by(SchoolClass.class_code)).scalars()}
    if not (sess_opts and cls_opts):
        st.info("Add an academic session and at least one class first "
                "(School Setup), then enrol students.")
    else:
        with st.form("bulk"):
            c1, c2 = st.columns(2)
            sess = c1.selectbox("Academic session", list(sess_opts.keys()))
            cls = c2.selectbox("Class", list(cls_opts.keys()))
            c3, c4 = st.columns(2)
            term_label = c3.selectbox("Term", list(_TERM_OPTS.keys()))
            inv_date = c4.date_input("Invoice date", value=None)
            annual = st.checkbox("Also include annual / one-off fees", value=False)
            if st.form_submit_button("Generate fees", type="primary"):
                try:
                    with get_session() as s:
                        res = school_billing.generate_class_fees(
                            s, class_id=cls_opts[cls],
                            academic_session_id=sess_opts[sess],
                            term_number=_TERM_OPTS[term_label],
                            invoice_date=inv_date, include_annual=annual)
                    msg = (f"Billed {res['billed']}, skipped {res['skipped']}"
                           + (f", {len(res['errors'])} error(s)"
                              if res["errors"] else ""))
                    for err in res["errors"]:
                        st.warning(err)
                    ui.flash(msg); st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ---- Record payment --------------------------------------------------------
with tab_pay:
    st.caption("Record a fee payment against an outstanding student invoice. "
               "Posts through the normal AR receipt engine (DR Bank / CR AR).")
    with get_session() as s:
        # unpaid student fee invoices: join billing -> invoice, keep outstanding>0
        unpaid = {}
        for b in s.execute(select(StudentFeeBilling).order_by(
                StudentFeeBilling.id.desc())).scalars():
            inv = b.sales_invoice
            stu = b.student
            if inv is None or stu is None:
                continue
            if inv.outstanding <= 0:
                continue
            label = (f"{stu.admission_no} · {stu.first_name} {stu.last_name} · "
                     f"{inv.number} · outstanding "
                     f"{inv.outstanding:,.2f}")
            unpaid[label] = (stu.id, inv.id, inv.outstanding)
        bank_opts = {f"{x.code} · {x.name}": x.id for x in s.execute(
            select(BankAccount).order_by(BankAccount.code)).scalars()}
    if not unpaid:
        st.info("No outstanding student fee invoices. Bill a class first, or "
                "all fees are fully paid.")
    elif not bank_opts:
        st.info("Add a bank account first.")
    else:
        with st.form("pay"):
            inv_label = st.selectbox("Student invoice", list(unpaid.keys()))
            sid, inv_id, outstanding = unpaid[inv_label]
            c1, c2 = st.columns(2)
            amount = c1.number_input("Amount", min_value=0.0,
                                     value=float(outstanding), step=1000.0)
            pay_date = c2.date_input("Payment date", value=None)
            c3, c4 = st.columns(2)
            bank_label = c3.selectbox("Bank account", list(bank_opts.keys()))
            method = c4.selectbox("Method", ["BANK", "CASH", "TRANSFER", "CARD"])
            reference = st.text_input("Reference", value="")
            if st.form_submit_button("Record payment", type="primary"):
                try:
                    with get_session() as s:
                        school_billing.record_fee_payment(
                            s, student_id=sid, sales_invoice_id=inv_id,
                            amount=amount, payment_date=pay_date,
                            bank_account_id=bank_opts[bank_label], method=method,
                            reference=reference or None)
                    ui.flash(f"Recorded payment of {amount:,.2f}."); st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ---- Fee status / defaulters -----------------------------------------------
with tab_status:
    st.caption("Class fee roll and the defaulters list for an academic session.")
    with get_session() as s:
        sess_opts = {x.session_code: x.id for x in s.execute(
            select(AcademicSession).order_by(
                AcademicSession.session_code)).scalars()}
        cls_opts = {c.class_code: c.id for c in s.execute(
            select(SchoolClass).order_by(SchoolClass.class_code)).scalars()}
    if not sess_opts:
        st.info("Add an academic session first.")
    else:
        c1, c2 = st.columns(2)
        sess_sel = c1.selectbox("Academic session", list(sess_opts.keys()),
                                key="status_sess")
        cls_sel = c2.selectbox("Class", list(cls_opts.keys()) if cls_opts
                               else ["—"], key="status_cls")
        with get_session() as s:
            roll = (school_billing.class_fee_status(
                s, class_id=cls_opts[cls_sel],
                academic_session_id=sess_opts[sess_sel]) if cls_opts else [])
            defs = school_billing.defaulters(
                s, academic_session_id=sess_opts[sess_sel])
        st.subheader(f"Class roll — {cls_sel}")
        if roll:
            ui.dataframe(pd.DataFrame(roll), hide_index=True, width="stretch")
        else:
            st.info("No billed students in this class for the session yet.")
        st.subheader("Defaulters (session)")
        if defs:
            ui.dataframe(pd.DataFrame(defs), hide_index=True, width="stretch")
            st.metric("Total outstanding",
                      f"{sum(d['outstanding'] for d in defs):,.2f}")
        else:
            st.success("No defaulters — all billed fees are settled.")


# ---- Billing log -----------------------------------------------------------
with tab_log:
    with get_session() as s:
        rows = [{"admission_no": (b.student.admission_no if b.student else ""),
                 "student": (f"{b.student.first_name} {b.student.last_name}"
                             if b.student else ""),
                 "session": (b.academic_session.session_code
                             if b.academic_session else ""),
                 "term": ("Annual" if b.term_number == 0 else f"T{b.term_number}"),
                 "invoice": (b.sales_invoice.number if b.sales_invoice else ""),
                 "amount": b.total_amount,
                 "billed": b.billing_date}
                for b in s.execute(select(StudentFeeBilling).order_by(
                    StudentFeeBilling.id.desc())).scalars()]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


auth.render_logout_in_sidebar()
