"""Notifications: overdue AR, upcoming bills, low stock, cash position.

Read-only operational alert board computed on the fly from the ledger /
master data. Also offers a one-click email digest (falls back to a copyable
plain-text block when SMTP isn't configured).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp.services import notifications
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Notifications · BizClinik ERP", layout="wide",
                   page_icon="🔔")
ui.inject_brand()
auth.require_login()
ui.hero("Notifications", "Overdue AR, upcoming bills, low stock, cash",
        badge="NT", right_label="Module", right_value="Alerts")


as_of = st.date_input("As of", value=date.today(), key="nt_asof")

with get_session() as s:
    digest = notifications.build_digest(s, as_of=as_of)

items = digest["items"]


# ---- KPI row --------------------------------------------------------------

ui.kpi_grid([
    {"label": "Overdue invoices", "value": str(digest["overdue_count"]),
     "delta": ui.money(digest["overdue_total"]), "delta_dir": "down",
     "color": "danger", "icon": "AR"},
    {"label": "Bills due (7d)", "value": str(digest["upcoming_count"]),
     "delta": ui.money(digest["upcoming_total"]), "delta_dir": "neutral",
     "color": "warning", "icon": "AP"},
    {"label": "Low stock items", "value": str(digest["low_stock_count"]),
     "color": "info", "icon": "ST"},
    {"label": "Cash position", "value": ui.money(digest["cash_total"]),
     "color": "danger" if digest["cash_below_threshold"] else "accent",
     "icon": "₦"},
])

if digest["cash_below_threshold"]:
    st.warning(f"Cash position {ui.money(digest['cash_total'])} is below the "
               "configured BIZCLINIK_CASH_ALERT threshold.")


# ---- sections -------------------------------------------------------------

ui.section("Overdue invoices", "POSTED / PARTIAL receivables past due")
overdue = items["overdue_invoices"]
if overdue:
    df = pd.DataFrame(overdue)
    df["due_date"] = df["due_date"].astype(str)
    df["outstanding"] = df["outstanding"].map(ui.money)
    df = df.rename(columns={
        "number": "Invoice", "customer": "Customer", "due_date": "Due",
        "days_overdue": "Days overdue", "outstanding": "Outstanding",
    })
    st.dataframe(df, hide_index=True, width="stretch")
else:
    st.success("No overdue invoices.")

ui.section("Upcoming bills", "Payables due within the next 7 days")
upcoming = items["upcoming_bills"]
if upcoming:
    df = pd.DataFrame(upcoming)
    df["due_date"] = df["due_date"].astype(str)
    df["outstanding"] = df["outstanding"].map(ui.money)
    df = df.rename(columns={
        "number": "Bill", "supplier": "Supplier", "due_date": "Due",
        "days_until": "Days until", "outstanding": "Outstanding",
    })
    st.dataframe(df, hide_index=True, width="stretch")
else:
    st.success("No bills due in the next 7 days.")

ui.section("Low stock", "Products below their reorder level")
low = items["low_stock"]
if low:
    df = pd.DataFrame(low)
    df["value_at_cost"] = df["value_at_cost"].map(ui.money)
    df = df.rename(columns={
        "sku": "SKU", "name": "Product", "qty_on_hand": "On hand",
        "avg_cost": "Avg cost", "value_at_cost": "Value at cost",
    })
    st.dataframe(df, hide_index=True, width="stretch")
else:
    st.success("All stock above reorder level.")

ui.section("Cash position", "Balance across bank accounts")
cash_accounts = items["cash_position"]["accounts"]
if cash_accounts:
    df = pd.DataFrame(cash_accounts)
    df["balance"] = df["balance"].map(ui.money)
    df = df.rename(columns={"code": "Code", "name": "Account", "balance": "Balance"})
    st.dataframe(df, hide_index=True, width="stretch")
else:
    st.caption("(no bank accounts configured)")


# ---- email digest ---------------------------------------------------------

with st.expander("Email digest", expanded=False):
    recipient = st.text_input("Recipient email", key="nt_to",
                              placeholder="someone@example.com")
    if st.button("Send digest", type="primary"):
        if not recipient:
            st.error("Enter a recipient email address first.")
        else:
            sent = notifications.send_digest_email(digest, to_addr=recipient)
            if sent:
                st.success(f"Digest sent to {recipient}.")
            else:
                st.info(
                    "SMTP is not configured (or the send failed). Set the "
                    "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS and SMTP_FROM "
                    "environment variables to enable email. Meanwhile, copy "
                    "the digest below:"
                )
                st.code(notifications.render_digest_text(digest))

auth.render_logout_in_sidebar()
