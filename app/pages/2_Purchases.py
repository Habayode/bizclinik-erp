"""Purchases: POs → Bills → Payments."""
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
    Account,
    BankAccount,
    Bill,
    DocStatus,
    Payment,
    Product,
    PurchaseOrder,
    Supplier,
)
from bizclinik_erp.services import purchase as p_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Purchases · BizClinik ERP", layout="wide",
                    page_icon="📥")
ui.inject_brand()
auth.require_login()
ui.hero("Purchases", "Purchase orders · Bills · Payments",
         badge="PU", right_label="Module", right_value="AP cycle")


tab_bill, tab_po, tab_pay = st.tabs(["🧾 Bills", "📋 Purchase orders", "💸 Payments"])


def _supplier_options(session) -> dict[str, int]:
    return {f"{s.code} — {s.name}": s.id
            for s in session.execute(select(Supplier).order_by(Supplier.name)).scalars()}


def _bank_options(session) -> dict[str, int]:
    return {f"{b.code} — {b.name}": b.id
            for b in session.execute(select(BankAccount).order_by(BankAccount.code)).scalars()}


def _product_options(session):
    return [{"id": p.id, "sku": p.sku, "name": p.name, "cost": p.standard_cost}
            for p in session.execute(select(Product).order_by(Product.sku)).scalars()]


def _expense_account_options(session) -> dict[str, int]:
    accts = session.execute(select(Account).where(
        Account.code.like("6%"), Account.is_postable == True  # noqa: E712
    ).order_by(Account.code)).scalars().all()
    return {f"{a.code} — {a.name}": a.id for a in accts}


with tab_bill:
    st.subheader("Bills")
    with get_session() as s:
        bills = s.execute(select(Bill).order_by(Bill.bill_date.desc())).scalars().all()
        rows = [{
            "number": b.number, "date": b.bill_date,
            "supplier": b.supplier.name if b.supplier else "",
            "total": b.grand_total, "paid": b.amount_paid,
            "outstanding": b.outstanding, "status": b.status.value,
        } for b in bills]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("New bill")
    with get_session() as s:
        sup_opts = _supplier_options(s)
        prods = _product_options(s)
        exp_opts = _expense_account_options(s)
    if not sup_opts:
        st.info("No suppliers yet.")
    else:
        with st.form("new_bill"):
            sel_sup = st.selectbox("Supplier", list(sup_opts.keys()))
            c1, c2 = st.columns(2)
            bdate = c1.date_input("Bill date", value=date.today())
            due = c2.date_input("Due date", value=date.today() + timedelta(days=30))
            line_type = st.radio("Line type", ["Inventory (stockable)", "Expense"],
                                  horizontal=True)
            seed = []
            if line_type.startswith("Inv") and prods:
                seed = [{"product_id": p["id"], "description": p["name"], "qty": 1,
                         "unit_cost": p["cost"], "tax_rate": 0.075,
                         "expense_account_id": None} for p in prods[:3]]
            else:
                default_acct = list(exp_opts.values())[0] if exp_opts else None
                seed = [{"product_id": None, "description": "", "qty": 1,
                         "unit_cost": 0.0, "tax_rate": 0.075,
                         "expense_account_id": default_acct}]
            grid = st.data_editor(pd.DataFrame(seed), num_rows="dynamic", key="bill_grid")
            notes = st.text_area("Notes")
            submit = st.form_submit_button("Receive bill", type="primary")
        if submit:
            lines = []
            for _, row in grid.iterrows():
                desc = str(row.get("description") or "").strip()
                if not desc:
                    continue
                lines.append(p_svc.POLineInput(
                    product_id=int(row["product_id"]) if pd.notna(row["product_id"]) else None,
                    description=desc, qty=float(row["qty"] or 0),
                    unit_cost=float(row["unit_cost"] or 0),
                    tax_rate=float(row["tax_rate"] or 0),
                    expense_account_id=int(row["expense_account_id"])
                    if pd.notna(row.get("expense_account_id")) else None,
                ))
            if not lines:
                st.error("Add at least one line.")
            else:
                with get_session() as s:
                    bill = p_svc.receive_bill(
                        s, supplier_id=sup_opts[sel_sup], bill_date=bdate,
                        due_date=due, lines=lines, notes=notes or None,
                    )
                    st.success(f"Bill {bill.number} posted — total ₦{bill.grand_total:,.2f}")


with tab_po:
    st.subheader("Purchase orders")
    with get_session() as s:
        pos = s.execute(select(PurchaseOrder).order_by(PurchaseOrder.order_date.desc())).scalars().all()
        rows = [{
            "number": o.number, "date": o.order_date,
            "supplier": o.supplier.name if o.supplier else "",
            "status": o.status.value,
        } for o in pos]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("New purchase order")
    with get_session() as s:
        sup_opts = _supplier_options(s)
        prods = _product_options(s)
    if not sup_opts:
        st.info("No suppliers yet — add one on the Settings page.")
    else:
        with st.form("new_po"):
            sel_sup = st.selectbox("Supplier", list(sup_opts.keys()), key="po_sup")
            order_date = st.date_input("Order date", value=date.today(), key="po_date")
            seed = [{"product_id": p["id"], "description": p["name"], "qty": 1,
                     "unit_cost": p["cost"], "tax_rate": 0.075}
                    for p in prods[:3]] or [{"product_id": None, "description": "",
                                                "qty": 1, "unit_cost": 0.0,
                                                "tax_rate": 0.075}]
            grid = st.data_editor(pd.DataFrame(seed), num_rows="dynamic", key="po_grid")
            notes = st.text_area("Notes", key="po_notes")
            submit = st.form_submit_button("Save purchase order", type="primary")
        if submit:
            lines = []
            for _, row in grid.iterrows():
                desc = str(row.get("description") or "").strip()
                if not desc:
                    continue
                lines.append(p_svc.POLineInput(
                    product_id=int(row["product_id"]) if pd.notna(row["product_id"]) else None,
                    description=desc, qty=float(row["qty"] or 0),
                    unit_cost=float(row["unit_cost"] or 0),
                    tax_rate=float(row["tax_rate"] or 0),
                ))
            if not lines:
                st.error("Add at least one line.")
            else:
                with get_session() as s:
                    po = p_svc.create_purchase_order(
                        s, supplier_id=sup_opts[sel_sup], order_date=order_date,
                        lines=lines, notes=notes or None,
                    )
                    st.success(f"Saved {po.number}")


with tab_pay:
    st.subheader("Payments")
    with get_session() as s:
        pays = s.execute(select(Payment).order_by(Payment.payment_date.desc())).scalars().all()
        rows = [{
            "number": p.number, "date": p.payment_date,
            "supplier": p.supplier.name if p.supplier else "",
            "bill": p.bill.number if p.bill else "",
            "amount": p.amount, "method": p.method, "status": p.status.value,
        } for p in pays]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Record payment")
    with get_session() as s:
        sup_opts = _supplier_options(s)
        bank_opts = _bank_options(s)
        bills = s.execute(select(Bill).where(
            Bill.status.in_([DocStatus.POSTED, DocStatus.PARTIAL])
        ).order_by(Bill.bill_date.desc())).scalars().all()
        bill_opts = {f"{b.number} ({b.supplier.name if b.supplier else '?'}) — "
                      f"₦{b.outstanding:,.2f} outstanding": b.id for b in bills}
    if sup_opts and bank_opts:
        with st.form("new_payment"):
            sel_sup = st.selectbox("Supplier", list(sup_opts.keys()), key="pay_sup")
            sel_bill = st.selectbox("Apply to bill (optional)",
                                     [""] + list(bill_opts.keys()), key="pay_bill")
            sel_bank = st.selectbox("Bank", list(bank_opts.keys()), key="pay_bank")
            amt = st.number_input("Amount (₦)", min_value=0.0, format="%.2f")
            method = st.selectbox("Method", ["BANK", "CASH", "CARD"], key="pay_method")
            ref = st.text_input("Reference", key="pay_ref")
            pdate = st.date_input("Payment date", value=date.today())
            submit = st.form_submit_button("Record payment", type="primary")
        if submit:
            with get_session() as s:
                pay = p_svc.record_payment(
                    s, supplier_id=sup_opts[sel_sup], payment_date=pdate,
                    amount=amt, bank_account_id=bank_opts[sel_bank],
                    bill_id=bill_opts.get(sel_bill) if sel_bill else None,
                    method=method, reference=ref or None,
                )
                st.success(f"Payment {pay.number} posted — ₦{pay.amount:,.2f}")

auth.render_logout_in_sidebar()
