"""Point of Sale — fast retail checkout (Supermarket / FMCG).

Scan or search an item, build the basket, tender, and complete the sale in one
tap. Behind the scenes it posts a full double-entry sale (revenue + VAT + COGS +
stock reduction) and settles the payment — see services/pos.py.
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
from bizclinik_erp.models import BankAccount, Product
from bizclinik_erp.services import pos as pos_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Point of Sale · Trakit365 ERP", layout="wide",
                   page_icon="🛒")
ui.inject_brand()
auth.require_login()
auth.require_perm("post.invoice")   # cashier
ui.hero("Point of Sale", "Scan · basket · tender · done", badge="POS",
        right_label="Module", right_value="Retail till", compact=True)

st.session_state.setdefault("pos_cart", [])

with get_session() as s:
    prods = [{
        "id": p.id, "sku": p.sku, "name": p.name,
        "price": float(p.standard_price or 0.0),
        "qty_on_hand": float(p.qty_on_hand or 0.0),
        "tax": float(p.tax_code.rate) if p.tax_code else 0.075,
    } for p in s.execute(
        select(Product).where(Product.is_active == True)  # noqa: E712
        .order_by(Product.name)).scalars()]
    banks = {f"{b.code} — {b.name}": b.id for b in s.execute(
        select(BankAccount).where(BankAccount.is_active == True)  # noqa: E712
        .order_by(BankAccount.code)).scalars()}

if not prods:
    st.info("No products yet. Add stock under **Inventory** (or bulk-import) first.")
    st.stop()

label_map = {f"{p['sku']} · {p['name']} — ₦{p['price']:,.2f}": p for p in prods}

# ---- scan / add ------------------------------------------------------------
with st.form("pos_scan", clear_on_submit=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    pick = c1.selectbox("Scan barcode / search item", [""] + list(label_map),
                        key="pos_pick")
    qty = c2.number_input("Qty", min_value=1.0, value=1.0, step=1.0, key="pos_qty")
    add = c3.form_submit_button("➕ Add", type="primary", use_container_width=True)
if add and pick:
    p = label_map[pick]
    cart = st.session_state["pos_cart"]
    for it in cart:
        if it["product_id"] == p["id"]:
            it["qty"] += float(qty)
            break
    else:
        cart.append({"product_id": p["id"], "sku": p["sku"], "name": p["name"],
                     "qty": float(qty), "price": p["price"], "tax": p["tax"],
                     "on_hand": p["qty_on_hand"]})
    st.rerun()

# ---- basket ----------------------------------------------------------------
cart = st.session_state["pos_cart"]
if not cart:
    st.info("Basket is empty — scan or search an item to begin.")
    st.stop()

rows = [{"S/N": i + 1, "Item": it["name"], "Qty": it["qty"],
         "Price": it["price"],
         "Line total": round(it["qty"] * it["price"] * (1 + it["tax"]), 2)}
        for i, it in enumerate(cart)]
ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

subtotal = round(sum(it["qty"] * it["price"] for it in cart), 2)
tax = round(sum(it["qty"] * it["price"] * it["tax"] for it in cart), 2)
total = round(subtotal + tax, 2)
m1, m2, m3 = st.columns(3)
m1.metric("Subtotal", ui.money(subtotal))
m2.metric("VAT", ui.money(tax))
m3.metric("Total", ui.money(total))

oversell = [it["name"] for it in cart if it["qty"] > it.get("on_hand", 0)]
if oversell:
    st.caption("⚠️ Selling more than on-hand for: " + ", ".join(oversell)
               + " (stock will go negative).")

e1, e2 = st.columns(2)
rem = e1.selectbox("Remove item", ["—"] + [f"{i + 1}. {it['name']}"
                                           for i, it in enumerate(cart)],
                   key="pos_rem")
if e1.button("Remove", key="pos_rembtn") and rem != "—":
    cart.pop(int(rem.split(".")[0]) - 1)
    st.rerun()
if e2.button("🗑 Clear basket", key="pos_clear", use_container_width=True):
    st.session_state["pos_cart"] = []
    st.rerun()

st.divider()

# ---- tender ----------------------------------------------------------------
t1, t2, t3 = st.columns(3)
method = t1.selectbox("Payment", ["CASH", "CARD", "TRANSFER"], key="pos_method")
sel_bank = t2.selectbox("Till / bank", list(banks), key="pos_bank")
tendered = None
if method == "CASH":
    tendered = t3.number_input("Cash tendered (₦)", min_value=0.0,
                               value=float(total), format="%.2f", key="pos_tender")
    if tendered >= total:
        st.caption(f"Change due: **{ui.money(round(tendered - total, 2))}**")

if st.button("✅ Complete sale", type="primary", key="pos_done",
             use_container_width=True):
    if not banks:
        st.error("No till/bank account — add one under **Banking** first.")
    elif method == "CASH" and (tendered or 0) < total:
        st.error("Cash tendered is less than the total.")
    else:
        lines = [pos_svc.CartLine(product_id=it["product_id"], qty=it["qty"],
                                  unit_price=it["price"], tax_rate=it["tax"])
                 for it in cart]
        try:
            with get_session() as s:
                res = pos_svc.checkout(s, lines=lines, bank_account_id=banks[sel_bank],
                                       method=method, tendered=tendered, on=date.today())
            st.session_state["pos_cart"] = []
            msg = f"Sale {res['invoice_number']} — {ui.money(res['total'])}"
            if res["change"]:
                msg += f" · change {ui.money(res['change'])}"
            ui.flash(msg + ".")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
