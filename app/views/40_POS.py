"""Point of Sale — fast retail checkout (Supermarket / FMCG).

Scan a barcode or search, build the basket (with per-line discounts), hold and
resume baskets, tender, and complete the sale — which posts a full double-entry
sale (revenue + VAT + COGS + stock-out), settles payment, and prints a receipt.
See services/pos.py.
"""
from __future__ import annotations

import html as _html
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.models import BankAccount, Company, Product
from bizclinik_erp.services import pos as pos_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Point of Sale · Trakit365 ERP", layout="wide",
                   page_icon="🛒")
ui.inject_brand()
auth.require_login()
auth.require_perm("post.invoice")   # cashier
ui.hero("Point of Sale", "Scan · basket · tender · print", badge="POS",
        right_label="Module", right_value="Retail till", compact=True)

st.session_state.setdefault("pos_cart", [])
st.session_state.setdefault("pos_held", [])
st.session_state.setdefault("pos_hold_n", 0)

with get_session() as s:
    _co = s.query(Company).first()
    store_name = _co.name if _co else "Trakit365"
    prods = [{
        "id": p.id, "sku": p.sku, "barcode": (p.barcode or ""), "name": p.name,
        "price": float(p.standard_price or 0.0),
        "qty_on_hand": float(p.qty_on_hand or 0.0),
        "tax": float(p.tax_code.rate) if p.tax_code else 0.075,
    } for p in s.execute(
        select(Product).where(Product.is_active == True)  # noqa: E712
        .order_by(Product.name)).scalars()]
    banks = {f"{b.code} — {b.name}": b.id for b in s.execute(
        select(BankAccount).where(BankAccount.is_active == True)  # noqa: E712
        .order_by(BankAccount.code)).scalars()}


def _receipt_html(r: dict) -> str:
    items = "".join(
        f"<tr><td>{_html.escape(str(it['name']))}</td>"
        f"<td class=q>{it['qty']:g} × ₦{it['price']:,.2f}</td>"
        f"<td class=a>₦{it['line_total']:,.2f}</td></tr>"
        for it in r.get("lines", []))
    tend = (f"<div class=row><span>Tendered</span><span>₦{r['tendered']:,.2f}"
            f"</span></div>" if r.get("tendered") else "")
    chg = (f"<div class=row><span>Change</span><span>₦{r['change']:,.2f}</span>"
           f"</div>" if r.get("change") else "")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    body{{font-family:'Segoe UI',system-ui,sans-serif;margin:0;color:#111}}
    #r{{width:300px;margin:6px auto;padding:14px;border:1px dashed #bbb}}
    h3{{text-align:center;margin:0 0 2px}}.meta{{text-align:center;color:#666;font-size:12px;margin-bottom:8px}}
    table{{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0}}
    td{{padding:2px 0;vertical-align:top}}.q{{color:#666;font-size:11px;text-align:center}}.a{{text-align:right;white-space:nowrap}}
    .row{{display:flex;justify-content:space-between;font-size:13px;padding:2px 0}}
    .tot{{font-weight:700;font-size:15px;border-top:1px solid #000;margin-top:4px;padding-top:4px}}
    .thanks{{text-align:center;color:#666;font-size:12px;margin-top:10px}}
    .pbtn{{display:block;margin:10px auto;padding:8px 16px;border:1px solid #0EA5A4;background:#0EA5A4;color:#04342C;border-radius:8px;font-weight:600;cursor:pointer}}
    @media print{{.pbtn{{display:none}}#r{{border:0}}}}
    </style></head><body>
    <div id="r">
      <h3>{_html.escape(store_name)}</h3>
      <div class="meta">{r['invoice_number']} · {r.get('date','')} · {r['method']}</div>
      <table>{items}</table>
      <div class="row"><span>Subtotal</span><span>₦{r['subtotal']:,.2f}</span></div>
      <div class="row"><span>VAT</span><span>₦{r['tax']:,.2f}</span></div>
      <div class="row tot"><span>TOTAL</span><span>₦{r['total']:,.2f}</span></div>
      {tend}{chg}
      <div class="thanks">Thank you for shopping!</div>
    </div>
    <button class="pbtn" onclick="window.print()">🖨 Print receipt</button>
    </body></html>"""


def _show_last_receipt() -> None:
    r = st.session_state.get("pos_last_receipt")
    if not r:
        return
    st.success(f"✅ Sale {r['invoice_number']} — {ui.money(r['total'])}"
               + (f" · change {ui.money(r['change'])}" if r.get("change") else ""))
    components.html(_receipt_html(r), height=260 + 24 * len(r.get("lines", [])))
    if st.button("Dismiss receipt", key="pos_dismiss"):
        st.session_state.pop("pos_last_receipt", None)
        st.rerun()


if not prods:
    st.info("No products yet. Add stock under **Inventory** (or bulk-import) first.")
    st.stop()

by_code = {}
for p in prods:
    by_code[p["sku"].lower()] = p
    if p["barcode"]:
        by_code[p["barcode"].lower()] = p
label_map = {f"{p['sku']} · {p['name']} — ₦{p['price']:,.2f}": p for p in prods}


def _add(p: dict, qty: float, disc: float) -> None:
    cart = st.session_state["pos_cart"]
    for it in cart:
        if it["product_id"] == p["id"] and it["discount"] == disc:
            it["qty"] += float(qty)
            return
    cart.append({"product_id": p["id"], "sku": p["sku"], "name": p["name"],
                 "qty": float(qty), "price": p["price"], "tax": p["tax"],
                 "discount": float(disc), "on_hand": p["qty_on_hand"]})


# ---- add item -------------------------------------------------------------
with st.form("pos_add", clear_on_submit=True):
    code = st.text_input("Scan barcode / SKU", key="pos_code",
                         help="Scan or type a barcode or SKU and press Enter — "
                              "or pick from search below.")
    pick = st.selectbox("…or search item", [""] + list(label_map), key="pos_pick")
    c1, c2, c3 = st.columns([1, 1, 1])
    qty = c1.number_input("Qty", min_value=1.0, value=1.0, step=1.0, key="pos_qty")
    disc = c2.number_input("Discount %", min_value=0.0, max_value=100.0,
                           value=0.0, step=1.0, key="pos_disc")
    add = c3.form_submit_button("➕ Add", type="primary", use_container_width=True)
if add:
    p = None
    if code.strip():
        p = by_code.get(code.strip().lower())
        if p is None:
            st.error(f"No product matches '{code.strip()}'.")
    elif pick:
        p = label_map[pick]
    if p:
        _add(p, qty, round(disc / 100.0, 4))
        st.rerun()

# ---- resume held baskets --------------------------------------------------
if st.session_state["pos_held"]:
    with st.expander(f"🅿 Held baskets ({len(st.session_state['pos_held'])})"):
        for i, h in enumerate(list(st.session_state["pos_held"])):
            hc = st.columns([3, 1, 1])
            hc[0].write(h["label"])
            if hc[1].button("Resume", key=f"pos_resume_{i}"):
                # merge any current lines into the resumed basket
                st.session_state["pos_cart"] = h["cart"] + st.session_state["pos_cart"]
                st.session_state["pos_held"].pop(i)
                st.rerun()
            if hc[2].button("Discard", key=f"pos_discard_{i}"):
                st.session_state["pos_held"].pop(i)
                st.rerun()

cart = st.session_state["pos_cart"]
if not cart:
    _show_last_receipt()
    st.info("Basket is empty — scan or search an item to begin.")
    st.stop()

# ---- basket ---------------------------------------------------------------
def _line_total(it) -> float:
    return round(it["qty"] * it["price"] * (1 - it["discount"]) * (1 + it["tax"]), 2)

rows = [{"S/N": i + 1, "Item": it["name"], "Qty": it["qty"], "Price": it["price"],
         "Disc %": round(it["discount"] * 100, 1), "Line total": _line_total(it)}
        for i, it in enumerate(cart)]
ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

subtotal = round(sum(it["qty"] * it["price"] * (1 - it["discount"]) for it in cart), 2)
tax = round(sum(it["qty"] * it["price"] * (1 - it["discount"]) * it["tax"]
                for it in cart), 2)
total = round(subtotal + tax, 2)
m1, m2, m3 = st.columns(3)
m1.metric("Subtotal", ui.money(subtotal))
m2.metric("VAT", ui.money(tax))
m3.metric("Total", ui.money(total))

oversell = [it["name"] for it in cart if it["qty"] > it.get("on_hand", 0)]
if oversell:
    st.caption("⚠️ Selling more than on-hand for: " + ", ".join(oversell)
               + " (stock will go negative).")

e1, e2, e3 = st.columns(3)
rem = e1.selectbox("Remove item", ["—"] + [f"{i + 1}. {it['name']}"
                                           for i, it in enumerate(cart)],
                   key="pos_rem")
if e1.button("Remove", key="pos_rembtn") and rem != "—":
    cart.pop(int(rem.split(".")[0]) - 1)
    st.rerun()
if e2.button("🅿 Hold basket", key="pos_hold", use_container_width=True):
    st.session_state["pos_hold_n"] += 1
    n = st.session_state["pos_hold_n"]
    st.session_state["pos_held"].append(
        {"label": f"Held #{n} · {len(cart)} item(s) · {ui.money(total)}", "cart": cart})
    st.session_state["pos_cart"] = []
    ui.flash(f"Basket held (#{n}).")
    st.rerun()
if e3.button("🗑 Clear", key="pos_clear", use_container_width=True):
    st.session_state["pos_cart"] = []
    st.rerun()

st.divider()

# ---- tender ---------------------------------------------------------------
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
                                  unit_price=it["price"], tax_rate=it["tax"],
                                  discount_pct=it["discount"]) for it in cart]
        try:
            with get_session() as s:
                res = pos_svc.checkout(s, lines=lines, bank_account_id=banks[sel_bank],
                                       method=method, tendered=tendered, on=date.today())
            st.session_state["pos_cart"] = []
            st.session_state["pos_last_receipt"] = {
                "store": store_name,
                "date": datetime.now().strftime("%d %b %Y %H:%M"), **res}
            msg = f"Sale {res['invoice_number']} — {ui.money(res['total'])}"
            if res["change"]:
                msg += f" · change {ui.money(res['change'])}"
            ui.flash(msg + ".")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
