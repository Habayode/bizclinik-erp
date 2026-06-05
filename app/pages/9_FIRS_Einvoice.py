"""FIRS E-Invoice: generate FIRS-compliant e-invoices from sales invoices."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import SalesInvoice
from bizclinik_erp.services import firs
from bizclinik_erp.exporters.firs_einvoice import build_einvoice_dict
from bizclinik_erp.exporters.qr import make_qr_png_bytes
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="FIRS E-Invoice · BizClinik ERP", layout="wide",
                    page_icon="🧾")
ui.inject_brand()
auth.require_login()
ui.hero("FIRS E-Invoice", "Generate FIRS-compliant e-invoices", badge="FI",
        right_label="Module", right_value="Tax compliance")


tab_gen, tab_subs = st.tabs(["🧾 Generate", "📜 Submissions"])


with tab_gen:
    ui.section("Generate e-invoice", "Build a FIRS-style payload from a sales invoice")
    with get_session() as s:
        invoices = list(
            s.execute(
                select(SalesInvoice).order_by(SalesInvoice.id.desc())
            ).scalars()
        )
        options = {f"{inv.number} (id {inv.id})": inv.id for inv in invoices}

    if not options:
        st.info("No sales invoices yet. Issue an invoice first.")
    else:
        label = st.selectbox("Invoice", list(options.keys()))
        invoice_id = options[label]
        if st.button("Generate e-invoice", type="primary"):
            with get_session() as s:
                submission = firs.generate_for_invoice(s, invoice_id)
                payload = json.loads(submission.payload_json)
                irn = submission.irn
                qr_payload = submission.qr_payload or ""

            st.success(f"Generated e-invoice — IRN {irn}")
            st.json(payload)

            st.download_button(
                "Download JSON",
                data=json.dumps(payload, indent=2, ensure_ascii=False),
                file_name=f"{irn}.json",
                mime="application/json",
                width="stretch",
            )

            try:
                png = make_qr_png_bytes(qr_payload)
                st.image(png, caption="FIRS e-invoice QR", width=240)
            except ImportError:
                st.info("Install the QR library to render a QR code: "
                        "pip install qrcode[pil]")


with tab_subs:
    ui.section("Submissions", "Previously generated FIRS e-invoices")
    with get_session() as s:
        subs = firs.list_submissions(s)
        rows = [{
            "ID": sub.id,
            "Invoice ID": sub.invoice_id,
            "IRN": sub.irn,
            "Status": sub.status.value,
            "Created": sub.created_at.strftime("%Y-%m-%d %H:%M"),
        } for sub in subs]

    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("(no submissions yet)")


auth.render_logout_in_sidebar()
