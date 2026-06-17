"""Data: view DB info and reset/maintenance."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from bizclinik_erp.config import get_settings
from bizclinik_erp.db import reset_db
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Data · Trakit365 ERP", layout="wide",
                    page_icon="💾")
ui.inject_brand()
auth.require_login()
# Operator-only: exposes the server DB path and a destructive wipe — not a
# tenant-facing feature. (Nav-hiding is cosmetic; this is the real gate.)
auth.require_platform_admin()
ui.hero("Data Management", "Database info · reset · maintenance",
         badge="DT", right_label="Module", right_value="Admin")

settings = get_settings()

st.subheader("Database")
c1, c2 = st.columns(2)
c1.text_input("DB path", value=str(settings.db_path), disabled=True)
c2.text_input("Currency", value=f"{settings.currency_code} ({settings.currency_symbol})",
               disabled=True)

st.divider()
st.subheader("Dangerous: wipe the DB")
st.caption("Drops all tables and recreates them empty. Confirms via a typed "
            "string so it can't be triggered by accident.")
confirm = st.text_input("Type DELETE to confirm")
if auth.has_perm("reset.db") and st.button("Reset database", type="secondary", disabled=confirm != "DELETE"):
    reset_db()
    st.success("Database reset.")

auth.render_logout_in_sidebar()
