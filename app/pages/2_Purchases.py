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
from bizclinik_erp.services import approvals
from bizclinik_erp.services import fx as fx_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Purchases · Trakit365 ERP", layout="wide",
                    page_icon="📥")
ui.inject_brand()
auth.require_login()
ui.hero("Purchases", "Purchase orders · Bills · Payments",
         badge="PU", right_label="Module", right_value="AP cycle")

_u = auth.current_user() or {}
UID, ROLE = _u.get("user_id"), _u.get("role")


def _gate_msg(res, posted_label: str):
    """Show the right message after an approval-gated action."""
    if res["status"] == "pending":
        lim = res.get("limit")
        lim_txt = f"₦{lim:,.0f}" if lim is not None else "your"
        st.warning(
            f"🔒 Above your approval limit ({lim_txt}) — submitted for approval "
            f"(request #{res['request_id']}). It will post once approved on the "
            "**Approvals** page.", icon="🔒")
    else:
        st.success(posted_label.format(ref=res["ref"]))


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
        with get_session() as s:
            from bizclinik_erp.models import Currency
            from sqlalchemy import select as _sel
            cur_codes = [c.code for c in s.execute(
                _sel(Currency).where(Currency.is_active == True)  # noqa: E712
                .order_by(Currency.is_base.desc(), Currency.code)).scalars()]
        with st.form("new_bill"):
            sel_sup = st.selectbox("Supplier", list(sup_opts.keys()))
            c1, c2, c3 = st.columns(3)
            bdate = c1.date_input("Bill date", value=date.today())
            due = c2.date_input("Due date", value=date.today() + timedelta(days=30))
            sel_cur = c3.selectbox("Currency", cur_codes or ["NGN"],
                                    help="Foreign bills post to the ledger in NGN "
                                         "at the latest rate; stock valued in NGN.")
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
            line_dicts = []
            for _, row in grid.iterrows():
                desc = str(row.get("description") or "").strip()
                if not desc:
                    continue
                line_dicts.append({
                    "product_id": int(row["product_id"]) if pd.notna(row["product_id"]) else None,
                    "description": desc, "qty": float(row["qty"] or 0),
                    "unit_cost": float(row["unit_cost"] or 0),
                    "tax_rate": float(row["tax_rate"] or 0),
                    "expense_account_id": int(row["expense_account_id"])
                    if pd.notna(row.get("expense_account_id")) else None,
                })
            if not line_dicts:
                st.error("Add at least one line.")
            else:
                try:
                    with get_session() as s:
                        rate = fx_svc.resolve_rate(s, sel_cur, fx_rate=None, as_of=bdate)
                        ngn_total = round(sum(
                            l["qty"] * l["unit_cost"] * (1 + l["tax_rate"])
                            for l in line_dicts) * rate, 2)
                        payload = {
                            "supplier_id": sup_opts[sel_sup],
                            "bill_date": bdate.isoformat(),
                            "due_date": due.isoformat() if due else None,
                            "lines": line_dicts, "notes": notes or None,
                            "currency_code": sel_cur, "fx_rate": rate,
                        }
                        res = approvals.gate(
                            s, doc_type="BILL", amount=ngn_total,
                            title=f"Bill — {sel_sup} (₦{ngn_total:,.0f})",
                            payload=payload, user_id=UID, role=ROLE)
                    _gate_msg(res, "Bill {ref} posted.")
                except ValueError as e:
                    st.error(str(e))


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
            line_dicts = []
            for _, row in grid.iterrows():
                desc = str(row.get("description") or "").strip()
                if not desc:
                    continue
                line_dicts.append({
                    "product_id": int(row["product_id"]) if pd.notna(row["product_id"]) else None,
                    "description": desc, "qty": float(row["qty"] or 0),
                    "unit_cost": float(row["unit_cost"] or 0),
                    "tax_rate": float(row["tax_rate"] or 0),
                    "expense_account_id": None,
                })
            if not line_dicts:
                st.error("Add at least one line.")
            else:
                ngn_total = round(sum(
                    l["qty"] * l["unit_cost"] * (1 + l["tax_rate"])
                    for l in line_dicts), 2)
                payload = {"supplier_id": sup_opts[sel_sup],
                           "order_date": order_date.isoformat(),
                           "lines": line_dicts, "notes": notes or None}
                with get_session() as s:
                    res = approvals.gate(
                        s, doc_type="PO", amount=ngn_total,
                        title=f"PO — {sel_sup} (₦{ngn_total:,.0f})",
                        payload=payload, user_id=UID, role=ROLE)
                _gate_msg(res, "Saved {ref}.")


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
            payload = {
                "supplier_id": sup_opts[sel_sup], "payment_date": pdate.isoformat(),
                "amount": amt, "bank_account_id": bank_opts[sel_bank],
                "bill_id": bill_opts.get(sel_bill) if sel_bill else None,
                "method": method, "reference": ref or None,
                "settlement_fx_rate": None,
            }
            with get_session() as s:
                res = approvals.gate(
                    s, doc_type="PAYMENT", amount=float(amt),
                    title=f"Payment — {sel_sup} (₦{amt:,.0f})",
                    payload=payload, user_id=UID, role=ROLE)
            _gate_msg(res, "Payment {ref} posted.")

auth.render_logout_in_sidebar()
