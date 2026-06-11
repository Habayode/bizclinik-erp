"""Trakit365 ERP — Dashboard (overview)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import (
    BankAccount,
    Bill,
    Company,
    Customer,
    JournalEntry,
    Product,
    SalesInvoice,
    Supplier,
)
from bizclinik_erp.services import reports
from bizclinik_erp.services.banking import bank_balance
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Dashboard · Trakit365 ERP", layout="wide",
                    page_icon="📊")
ui.inject_brand()
auth.require_login()


with get_session() as s:
    company = s.query(Company).first()

if not company:
    ui.hero("Trakit365 ERP", "Set up your company to get started",
            badge="BE")
    st.info(
        "**No company configured.** Open **Settings** to set the company "
        "profile, or **Data** to import a BizClinik xlsx workbook."
    )
    st.stop()


today = date.today()
fy_start = date(today.year, 1, 1)

with get_session() as s:
    n_customers = s.query(Customer).count()
    n_suppliers = s.query(Supplier).count()
    n_products = s.query(Product).count()
    n_invoices = s.query(SalesInvoice).count()
    n_bills = s.query(Bill).count()

    pnl = reports.profit_and_loss(s, period_start=fy_start, period_end=today)
    bs = reports.balance_sheet(s, as_of=today)
    ar_aging = reports.ar_aging(s, as_of=today)
    ap_aging = reports.ap_aging(s, as_of=today)

    banks = s.execute(select(BankAccount).where(BankAccount.is_active == True)  # noqa: E712
                       ).scalars().all()
    bank_rows = [{"name": f"{b.code} · {b.name}",
                   "balance": bank_balance(s, b.id) or 0.0} for b in banks]
    total_cash = round(sum(r["balance"] for r in bank_rows), 2)

    # Build monthly P&L series for the trend chart.
    monthly = []
    for m in range(1, today.month + 1):
        m_start = date(today.year, m, 1)
        m_end = (date(today.year, m + 1, 1) if m < 12 else date(today.year + 1, 1, 1)) - timedelta(days=1)
        rp = reports.profit_and_loss(s, period_start=m_start, period_end=m_end)
        monthly.append({
            "month": m_start.strftime("%b"),
            "revenue": rp["total_revenue"],
            "expense": rp["total_direct_costs"] + rp["total_operating_expenses"],
            "net": rp["net_profit"],
        })

    # Recent journals for activity feed.
    recent_jes = s.execute(select(JournalEntry).order_by(
        JournalEntry.posted_at.desc().nullslast(),
        JournalEntry.id.desc()
    ).limit(8)).scalars().all()
    recent_rows = [{
        "Date": j.entry_date.isoformat(),
        "JE": j.entry_no,
        "Source": (j.source_kind or "Manual").replace("_", " "),
        "Memo": (j.memo or "")[:90],
        "Amount": ui.money(j.total_debit),
    } for j in recent_jes]


# ---- Hero -------------------------------------------------------------------

ui.hero(
    title=company.name,
    subtitle=" · ".join(filter(None, [company.rc_number, company.address])) or "Welcome",
    badge=company.name,
    right_label=f"As of {today.strftime('%d %b %Y')}",
    right_value=f"FY {today.year}",
)


# ---- Headline KPIs ----------------------------------------------------------

net_dir = "up" if pnl["net_profit"] >= 0 else "down"
ui.kpi_grid([
    {"label": "Revenue YTD", "value": ui.money(pnl["total_revenue"]),
     "icon": "₦", "color": "accent",
     "delta": f"{n_invoices} invoices", "delta_dir": "neutral"},
    {"label": "Direct costs", "value": ui.money(pnl["total_direct_costs"]),
     "icon": "↓", "color": "primary"},
    {"label": "Operating expenses", "value": ui.money(pnl["total_operating_expenses"]),
     "icon": "⚙", "color": "primary"},
    {"label": "Net profit", "value": ui.money(pnl["net_profit"]),
     "icon": "★", "color": "success" if pnl["net_profit"] >= 0 else "danger",
     "delta": "profit" if pnl["net_profit"] >= 0 else "loss",
     "delta_dir": net_dir},
])

ar_total = round(sum(r["total"] for r in ar_aging), 2)
ap_total = round(sum(r["total"] for r in ap_aging), 2)

ui.kpi_grid([
    {"label": "Cash & bank", "value": ui.money(total_cash),
     "icon": "🏦", "color": "info"},
    {"label": "Inventory at cost", "value": ui.money(
        sum(r["amount"] for r in bs["assets"] if r["code"] == "1140")),
     "icon": "📦", "color": "primary"},
    {"label": "AR outstanding", "value": ui.money(ar_total),
     "icon": "→", "color": "warning",
     "delta": f"{len(ar_aging)} customers", "delta_dir": "neutral"},
    {"label": "AP outstanding", "value": ui.money(ap_total),
     "icon": "←", "color": "danger",
     "delta": f"{len(ap_aging)} suppliers", "delta_dir": "neutral"},
])

ui.kpi_grid([
    {"label": "Total assets", "value": ui.money(bs["total_assets"]),
     "color": "primary"},
    {"label": "Total liabilities", "value": ui.money(bs["total_liabilities"]),
     "color": "primary"},
    {"label": "Total equity", "value": ui.money(bs["total_equity"]),
     "color": "primary"},
    {"label": "Balance sheet", "value": "Balanced" if bs["balanced"] else "Off",
     "color": "success" if bs["balanced"] else "danger",
     "icon": "✓" if bs["balanced"] else "!",
     "delta": "A = L + E" if bs["balanced"] else f"diff {ui.money(bs['imbalance'])}",
     "delta_dir": "up" if bs["balanced"] else "down"},
])


# ---- Charts row -------------------------------------------------------------

ui.section("Performance", f"{today.year} year-to-date by month")
chart_col, exp_col = st.columns([1.4, 1])
with chart_col:
    df_month = pd.DataFrame(monthly)
    if df_month["revenue"].sum() + df_month["expense"].sum() > 0:
        st.altair_chart(ui.revenue_vs_expense_chart(df_month), width='stretch')
    else:
        st.caption("No revenue or expense activity yet.")

with exp_col:
    rows = []
    for r in pnl["operating_expenses"]:
        rows.append({"name": r["name"], "amount": r["amount"]})
    for r in pnl["direct_costs"]:
        rows.append({"name": r["name"], "amount": r["amount"]})
    df_exp = pd.DataFrame(rows)
    if not df_exp.empty:
        st.markdown("**Expenses by account**")
        st.altair_chart(ui.expense_breakdown_chart(df_exp), width='stretch')
    else:
        st.caption("No expenses recorded.")


# ---- Cash + aging row ------------------------------------------------------

ui.section("Liquidity & exposure", "Cash position and what's owed")
cash_col, ar_col, ap_col = st.columns(3)

with cash_col:
    st.markdown("**Cash position**")
    if bank_rows:
        st.altair_chart(ui.cash_position_chart(bank_rows), width='stretch')
    else:
        st.caption("No bank accounts.")

with ar_col:
    st.markdown("**Accounts receivable aging**")
    if ar_aging:
        df_ar = pd.DataFrame(ar_aging)
        st.altair_chart(ui.aging_bar_chart(df_ar, "customer_name"),
                         width='stretch')
    else:
        st.caption("Nothing outstanding.")

with ap_col:
    st.markdown("**Accounts payable aging**")
    if ap_aging:
        df_ap = pd.DataFrame(ap_aging)
        st.altair_chart(ui.aging_bar_chart(df_ap, "supplier_name"),
                         width='stretch')
    else:
        st.caption("Nothing outstanding.")


# ---- Recent activity + master-data counts ----------------------------------

ui.section("Recent activity", "Last 8 journal entries")
left, right = st.columns([2, 1])
with left:
    if recent_rows:
        st.dataframe(pd.DataFrame(recent_rows), hide_index=True,
                      width='stretch', height=320)
    else:
        st.caption("No journal entries yet.")

with right:
    muted = ui.BRAND["muted"]
    ink = ui.BRAND["ink"]
    def _tile(label: str, value) -> str:
        return (
            f"<div><div style='color:{muted};font-size:0.75rem;"
            f"text-transform:uppercase;letter-spacing:0.06em'>{label}</div>"
            f"<div style='font-size:1.1rem;font-weight:700'>{value}</div></div>"
        )
    master_html = (
        "<div class='surface'>"
        "<h3>Master data</h3>"
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:6px'>"
        f"{_tile('Customers', n_customers)}"
        f"{_tile('Suppliers', n_suppliers)}"
        f"{_tile('Products', n_products)}"
        f"{_tile('Bank accounts', len(banks))}"
        f"{_tile('Invoices', n_invoices)}"
        f"{_tile('Bills', n_bills)}"
        "</div></div>"
    )
    st.markdown(ui._h(master_html), unsafe_allow_html=True)

    shortcuts_html = (
        "<div class='surface'>"
        "<h3>Shortcuts</h3>"
        f"<ul style='padding-left:18px;margin-bottom:0;color:{ink}'>"
        "<li>📝 Issue a new invoice → <b>Sales</b></li>"
        "<li>📥 Receive a bill → <b>Purchases</b></li>"
        "<li>📦 Check stock levels → <b>Inventory</b></li>"
        "<li>📈 P&amp;L · BS · Cash flow → <b>Reports</b></li>"
        "</ul></div>"
    )
    st.markdown(ui._h(shortcuts_html), unsafe_allow_html=True)

auth.render_logout_in_sidebar()
