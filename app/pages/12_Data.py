"""Data: import BizClinik xlsx, reset DB, view DB info."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.config import get_settings
from bizclinik_erp.db import get_session, reset_db
from bizclinik_erp.importers.bizclinik_xlsx import import_workbook
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Data · BizClinik ERP", layout="wide",
                    page_icon="💾")
ui.inject_brand()
auth.require_login()
ui.hero("Data Management", "Import legacy workbooks · reset · maintenance",
         badge="DT", right_label="Module", right_value="Admin")

settings = get_settings()

st.subheader("Database")
c1, c2 = st.columns(2)
c1.text_input("DB path", value=str(settings.db_path), disabled=True)
c2.text_input("Currency", value=f"{settings.currency_code} ({settings.currency_symbol})",
               disabled=True)

st.divider()
st.subheader("Import BizClinik workbook")
st.caption("Pulls in master data (customers, suppliers, products) and posts a "
            "bill for every supplier row, an invoice for every customer row, "
            "and an opex bill for every operating-module row. Existing master "
            "records are reused by name.")
source = st.radio("Source", ["Upload file", "Local path"], horizontal=True)
xlsx_path = None
if source == "Upload file":
    f = st.file_uploader("Workbook (.xlsx)", type=["xlsx"])
    if f is not None:
        tmp = Path(tempfile.gettempdir()) / f"bizclinik_import_{f.name}"
        tmp.write_bytes(f.getvalue())
        xlsx_path = tmp
else:
    p = st.text_input("Path",
                       value=r"C:\Users\User\Downloads\BizClinik Accounting and Business Software- Wendysrack Luxe Ltd.xlsx")
    if p and Path(p).exists():
        xlsx_path = Path(p)
    elif p:
        st.error(f"File not found: {p}")

reset_before = st.checkbox("Reset database first (destructive)", value=False,
                            help="Drops and recreates all tables before importing.")
if xlsx_path and st.button("Run import", type="primary"):
    with st.spinner("Importing…"):
        if reset_before:
            reset_db()
        with get_session() as s:
            summary = import_workbook(s, xlsx_path)
    st.success("Import complete.")
    st.json({k: v for k, v in summary.items() if k != "skipped"})
    if summary.get("skipped"):
        st.warning(f"{len(summary['skipped'])} rows skipped.")
        st.dataframe(pd.DataFrame(summary["skipped"]), hide_index=True, width="stretch")

st.divider()
st.subheader("Dangerous: wipe the DB")
st.caption("Drops all tables and recreates them empty. Confirms via a typed "
            "string so it can't be triggered by accident.")
confirm = st.text_input("Type DELETE to confirm")
if st.button("Reset database", type="secondary", disabled=confirm != "DELETE"):
    reset_db()
    st.success("Database reset.")

auth.render_logout_in_sidebar()
