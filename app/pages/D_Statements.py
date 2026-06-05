"""Statements: customer SOA + WHT credit note exports."""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
import tempfile
import uuid
from datetime import date
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.exporters.customer_statement_pdf import (
    write_customer_statement_pdf,
)
from bizclinik_erp.exporters.wht_certificate_pdf import write_wht_certificate_pdf
from bizclinik_erp.models import Customer, Supplier
from bizclinik_erp.services.customer_statement import (
    customer_ledger,
    customer_outstanding,
)
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="Statements · BizClinik ERP", layout="wide",
                    page_icon="📄")
ui.inject_brand()
auth.require_login()
ui.hero("Statements", "Customer SOA · WHT certificates",
         badge="ST", right_label="Module", right_value="Communications")


def _money(x: float) -> str:
    return ui.money(x)


def _try_send_email(to_addr: str, subject: str, body: str,
                    attachment: Path) -> tuple[bool, str]:
    """Send the PDF via SMTP if env is configured. Returns (ok, message)."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        return False, ("SMTP not configured. Set SMTP_HOST / SMTP_PORT / "
                       "SMTP_USER / SMTP_PASSWORD / SMTP_FROM env vars.")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pw = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", user or "noreply@example.com")
    use_tls = os.environ.get("SMTP_TLS", "1") != "0"

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    data = attachment.read_bytes()
    msg.add_attachment(
        data, maintype="application", subtype="pdf",
        filename=attachment.name,
    )
    try:
        if use_tls:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ctx)
                if user:
                    s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                if user:
                    s.login(user, pw)
                s.send_message(msg)
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return False, f"Send failed: {exc}"
    return True, f"Sent to {to_addr}."


tab_soa, tab_wht = st.tabs(
    ["📄 Customer Statement", "🧾 WHT Certificate"]
)


# ---- Customer SOA tab ------------------------------------------------------

with tab_soa:
    with get_session() as s:
        customers = s.execute(
            select(Customer).where(Customer.is_active.is_(True))
            .order_by(Customer.name)
        ).scalars().all()
        customer_options = {c.id: f"{c.code} — {c.name}" for c in customers}

    if not customer_options:
        st.info("No active customers. Add one on the Sales page first.")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        cust_id = c1.selectbox(
            "Customer", list(customer_options.keys()),
            format_func=lambda k: customer_options[k], key="soa_cust",
        )
        ps = c2.date_input(
            "Period start", value=date(date.today().year, 1, 1), key="soa_ps",
        )
        pe = c3.date_input("Period end", value=date.today(), key="soa_pe")

        with get_session() as s:
            rows = customer_ledger(s, cust_id, period_start=ps, period_end=pe)
            outstanding = customer_outstanding(s, cust_id, as_of=pe)

        a, b, c = st.columns(3)
        a.metric("Outstanding (as of period end)", _money(outstanding))
        b.metric("Lines in window", str(len(rows)))
        c.metric(
            "Closing balance",
            _money(rows[-1]["running_balance"] if rows else outstanding),
        )

        st.markdown("#### Ledger preview")
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption("(no postings in window)")

        st.markdown("#### Export")
        gen_col, email_col = st.columns([1, 2])
        with gen_col:
            if st.button("Generate PDF", type="primary", key="soa_gen"):
                tmpdir = Path(tempfile.mkdtemp(prefix="soa_"))
                fname = (
                    f"SOA_{customer_options[cust_id].split(' — ')[0]}_"
                    f"{pe.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}.pdf"
                )
                out_path = tmpdir / fname
                with get_session() as s:
                    write_customer_statement_pdf(
                        s, cust_id, period_start=ps, period_end=pe,
                        out_path=out_path,
                    )
                st.session_state["_soa_last_pdf"] = str(out_path)
                st.success(f"Generated: {out_path.name}")

        last_pdf = st.session_state.get("_soa_last_pdf")
        if last_pdf and Path(last_pdf).exists():
            with open(last_pdf, "rb") as fh:
                st.download_button(
                    "Download statement PDF", fh, file_name=Path(last_pdf).name,
                    mime="application/pdf", key="soa_dl",
                )

        with email_col:
            st.markdown("**Email statement (optional)**")
            to_addr = st.text_input(
                "Recipient", value="", key="soa_to",
                placeholder="finance@customer.example",
            )
            if st.button("Send via email", key="soa_send"):
                if not last_pdf or not Path(last_pdf).exists():
                    st.warning("Generate the PDF first.")
                elif not to_addr:
                    st.warning("Enter a recipient email.")
                else:
                    ok, msg = _try_send_email(
                        to_addr,
                        subject=f"Statement of Account — "
                                f"{customer_options[cust_id]}",
                        body=("Please find attached your statement of account "
                              f"for the period {ps} to {pe}."),
                        attachment=Path(last_pdf),
                    )
                    (st.success if ok else st.info)(msg)


# ---- WHT certificate tab ---------------------------------------------------

with tab_wht:
    with get_session() as s:
        suppliers = s.execute(
            select(Supplier).where(Supplier.is_active.is_(True))
            .order_by(Supplier.name)
        ).scalars().all()
        supplier_options = {sp.id: f"{sp.code} — {sp.name}" for sp in suppliers}

    if not supplier_options:
        st.info("No active suppliers. Add one on the Purchases page first.")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        sup_id = c1.selectbox(
            "Supplier", list(supplier_options.keys()),
            format_func=lambda k: supplier_options[k], key="wht_sup",
        )
        ps = c2.date_input(
            "Period start", value=date(date.today().year, 1, 1), key="wht_ps",
        )
        pe = c3.date_input("Period end", value=date.today(), key="wht_pe")

        from bizclinik_erp.exporters.wht_certificate_pdf import _collect_wht_rows
        with get_session() as s:
            from bizclinik_erp.config import get_settings
            rows = _collect_wht_rows(
                s, sup_id,
                period_start=ps, period_end=pe,
                wht_rate=get_settings().default_wht_rate,
            )

        a, b = st.columns(2)
        a.metric("Bills with WHT", str(len(rows)))
        b.metric("Total WHT", _money(sum(r["wht"] for r in rows)))

        st.markdown("#### Detail preview")
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption(
                "(no WHT-bearing bills in window — try a wider period or post "
                "a bill with the WHT5 tax code)"
            )

        if st.button("Generate PDF", type="primary", key="wht_gen"):
            tmpdir = Path(tempfile.mkdtemp(prefix="wht_"))
            fname = (
                f"WHT_{supplier_options[sup_id].split(' — ')[0]}_"
                f"{pe.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}.pdf"
            )
            out_path = tmpdir / fname
            with get_session() as s:
                write_wht_certificate_pdf(
                    s, sup_id, period_start=ps, period_end=pe,
                    out_path=out_path,
                )
            st.session_state["_wht_last_pdf"] = str(out_path)
            st.success(f"Generated: {out_path.name}")

        wht_last = st.session_state.get("_wht_last_pdf")
        if wht_last and Path(wht_last).exists():
            with open(wht_last, "rb") as fh:
                st.download_button(
                    "Download WHT certificate PDF", fh,
                    file_name=Path(wht_last).name,
                    mime="application/pdf", key="wht_dl",
                )


auth.render_logout_in_sidebar()
