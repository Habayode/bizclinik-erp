"""Inventory: products, stock card, valuation, manual adjustments."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import Product
from bizclinik_erp.services import inventory as inv_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Inventory · Trakit365 ERP", layout="wide",
                    page_icon="📦")
ui.inject_brand()
auth.require_login()
auth.require_perm("manage.products")
ui.hero("Inventory", "Weighted-average cost · stock cards · adjustments",
         badge="IN", right_label="Module", right_value="Stock")

tab_val, tab_card, tab_prods, tab_adj = st.tabs(
    ["💎 Valuation", "📋 Stock card", "🏷️ Products", "⚖️ Adjustment"]
)

with tab_val:
    with get_session() as s:
        rows = inv_svc.inventory_valuation(s)
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, width="stretch")
        st.metric("Total inventory at cost", f"₦{df['value_at_cost'].sum():,.2f}")
        below = df[df["below_reorder"]]
        if not below.empty:
            st.warning(f"{len(below)} product(s) below reorder level:")
            st.dataframe(below[["sku", "name", "qty_on_hand"]], hide_index=True,
                         width="stretch")
    else:
        st.info("No stockable products yet.")


with tab_card:
    with get_session() as s:
        prods = s.execute(select(Product).order_by(Product.sku)).scalars().all()
        opts = {f"{p.sku} — {p.name}": p.id for p in prods}
    if opts:
        sel = st.selectbox("Product", list(opts.keys()))
        with get_session() as s:
            card = inv_svc.stock_card(s, opts[sel])
        if card:
            st.dataframe(pd.DataFrame(card), hide_index=True, width="stretch")
        else:
            st.caption("No movements yet.")
    else:
        st.info("Add a product first.")


with tab_prods:
    with get_session() as s:
        prods = s.execute(select(Product).order_by(Product.sku)).scalars().all()
        rows = [{
            "id": p.id, "sku": p.sku, "name": p.name,
            "unit": p.unit, "qty_on_hand": p.qty_on_hand,
            "avg_cost": p.avg_cost, "standard_price": p.standard_price,
            "reorder_level": p.reorder_level, "stockable": p.is_stockable,
            "active": p.is_active,
        } for p in prods]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    ui.bulk_import_expander("product", "Products")
    st.divider()
    st.subheader("Add product")
    with st.form("new_product"):
        sku = st.text_input("SKU")
        name = st.text_input("Name")
        unit = st.text_input("Unit", value="ea")
        price = st.number_input("Standard price (₦)", min_value=0.0, format="%.2f")
        cost = st.number_input("Standard cost (₦)", min_value=0.0, format="%.2f")
        reorder = st.number_input("Reorder level", min_value=0.0, format="%.2f")
        stockable = st.checkbox("Stockable", value=True)
        submit = st.form_submit_button("Save", type="primary")
    if submit:
        if not sku or not name:
            st.error("SKU and name are required.")
        else:
            with get_session() as s:
                s.add(Product(sku=sku.strip(), name=name.strip(),
                               unit=unit or "ea",
                               standard_price=price, standard_cost=cost,
                               reorder_level=reorder, is_stockable=stockable))
            st.success(f"Added product {sku}")


with tab_adj:
    with get_session() as s:
        prods = s.execute(select(Product).order_by(Product.sku)).scalars().all()
        opts = {f"{p.sku} — {p.name}": p.id for p in prods}
    if opts:
        with st.form("adjust"):
            sel = st.selectbox("Product", list(opts.keys()), key="adj_sel")
            qty = st.number_input("Qty delta (+/-)", format="%.4f")
            unit_cost = st.number_input("Unit cost (₦) — for stock-in only",
                                         min_value=0.0, format="%.2f", value=0.0)
            memo = st.text_input("Memo")
            on = st.date_input("Date", value=date.today())
            submit = st.form_submit_button("Apply", type="primary")
        if submit and qty != 0:
            with get_session() as s:
                mv = inv_svc.adjust_stock(
                    s, opts[sel], on=on, qty_delta=qty,
                    unit_cost=unit_cost or None, memo=memo or None,
                )
                st.success(f"Adjustment recorded — on hand now {mv.qty_on_hand_after}")

auth.render_logout_in_sidebar()
