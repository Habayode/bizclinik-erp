"""Store Dashboard — retail/supermarket view: takings, baskets, movers, restock."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Product, SalesInvoice, StockMovement
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Store Dashboard · Trakit365 ERP", layout="wide",
                   page_icon="🏪")
ui.inject_brand()
auth.require_login()
auth.require_perm("view.dashboard")
ui.hero("Store Dashboard", "Today's takings · baskets · movers · restock",
        badge="ST", right_label="As of", right_value=date.today().strftime("%d %b %Y"),
        compact=True)

today = date.today()
week_start = today - timedelta(days=6)

with get_session() as s:
    inv_today = s.execute(select(SalesInvoice).where(
        SalesInvoice.invoice_date == today)).scalars().all()
    takings = round(sum(i.grand_total for i in inv_today), 2)
    txns = len(inv_today)

    # 7-day takings by day.
    week = []
    for d in (week_start + timedelta(days=k) for k in range(7)):
        tot = s.execute(select(func.coalesce(func.sum(SalesInvoice.grand_total), 0.0))
                        .where(SalesInvoice.invoice_date == d)).scalar_one()
        week.append({"day": d.strftime("%a %d"), "sales": round(float(tot), 2)})

    low = s.execute(select(Product).where(
        Product.is_stockable == True,  # noqa: E712
        Product.reorder_level > 0,
        Product.qty_on_hand < Product.reorder_level).order_by(Product.name)
    ).scalars().all()
    low_rows = [{"S/N": i + 1, "SKU": p.sku, "Item": p.name,
                 "On hand": p.qty_on_hand, "Reorder at": p.reorder_level}
                for i, p in enumerate(low)]

    cutoff = today - timedelta(days=30)
    movers = s.execute(
        select(Product.name, func.sum(StockMovement.qty_out).label("sold"))
        .join(StockMovement, StockMovement.product_id == Product.id)
        .where(StockMovement.qty_out > 0, StockMovement.movement_date >= cutoff)
        .group_by(Product.name).order_by(func.sum(StockMovement.qty_out).desc())
        .limit(10)).all()
    mover_rows = [{"S/N": i + 1, "Item": n, "Units sold (30d)": round(float(q), 2)}
                  for i, (n, q) in enumerate(movers)]

# ---- KPIs ------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Sales today", ui.money(takings))
k2.metric("Transactions today", txns)
k3.metric("Average basket", ui.money(round(takings / txns, 2) if txns else 0.0))
k4.metric("Items below reorder", len(low))

# ---- week ------------------------------------------------------------------
ui.section("Last 7 days", "Daily takings")
wdf = pd.DataFrame(week)
if wdf["sales"].sum() > 0:
    st.bar_chart(wdf.set_index("day")["sales"])
else:
    st.caption("No sales recorded in the last 7 days yet.")

# ---- movers + restock ------------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    ui.section("Top sellers", "Units sold in the last 30 days")
    if mover_rows:
        ui.dataframe(pd.DataFrame(mover_rows), hide_index=True, width="stretch")
    else:
        st.caption("No sales movement yet.")
with c2:
    ui.section("Restock list", "Below reorder level")
    if low_rows:
        ui.dataframe(pd.DataFrame(low_rows), hide_index=True, width="stretch")
        st.page_link("views/2_Purchases.py", label="→ Raise a purchase order",
                     icon="📥")
    else:
        st.success("Everything is above its reorder level.")
