"""Sales: quotations → orders → invoices → receipts."""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from bizclinik_erp.db import get_session
from bizclinik_erp.exporters.invoice_pdf import write_invoice_pdf
from bizclinik_erp.models import (
    BankAccount,
    Customer,
    DocStatus,
    Product,
    Quotation,
    Receipt,
    SalesInvoice,
    SalesOrder,
)
from bizclinik_erp.services import sales as sales_svc
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="Sales · Trakit365 ERP", layout="wide",
                    page_icon="📝")
ui.inject_brand()
auth.require_login()
auth.require_perm("post.invoice")
ui.hero("Sales", "Quotations · Sales orders · Invoices · Receipts",
         badge="SL", right_label="Module", right_value="AR cycle")


tab_inv, tab_quote, tab_so, tab_rct = st.tabs(
    ["📄 Invoices", "📝 Quotations", "🧾 Sales orders", "💰 Receipts"]
)


# ----- shared helpers -------------------------------------------------------


def _customer_options(session) -> dict[str, int]:
    rows = session.execute(select(Customer).order_by(Customer.name)).scalars().all()
    return {f"{c.code} — {c.name}": c.id for c in rows}


def _product_options(session) -> list[dict]:
    rows = session.execute(select(Product).order_by(Product.sku)).scalars().all()
    return [{"id": p.id, "sku": p.sku, "name": p.name,
             "price": p.standard_price} for p in rows]


def _bank_options(session) -> dict[str, int]:
    rows = session.execute(select(BankAccount).order_by(BankAccount.code)).scalars().all()
    return {f"{b.code} — {b.name}": b.id for b in rows}


# ----- Invoices tab ---------------------------------------------------------


with tab_inv:
    st.subheader("Invoices")
    fc1, fc2 = st.columns([1, 2])
    f_status = fc1.selectbox(
        "Status", ["All", "POSTED", "PARTIAL", "PAID", "CANCELLED"],
        key="inv_f_status")
    f_text = fc2.text_input("Search (number or customer)", key="inv_f_text")
    with get_session() as s:
        invs = s.execute(
            select(SalesInvoice).order_by(SalesInvoice.invoice_date.desc())
        ).scalars().all()
        rows = [{
            "id": i.id,
            "number": i.number,
            "date": i.invoice_date,
            "customer": i.customer.name if i.customer else "",
            "total": i.grand_total,
            "paid": i.amount_paid,
            "outstanding": i.outstanding,
            "status": i.status.value,
        } for i in invs]
    if f_status != "All":
        rows = [r for r in rows if r["status"] == f_status]
    if f_text.strip():
        _q = f_text.strip().lower()
        rows = [r for r in rows
                if _q in r["number"].lower() or _q in r["customer"].lower()]
    sel_inv = None
    if rows:
        sel_inv = ui.pick_row(
            pd.DataFrame(rows), key="inv_pick",
            column_config={"total": ui.money_col("total"),
                           "paid": ui.money_col("paid"),
                           "outstanding": ui.money_col("outstanding"),
                           "id": None})
    else:
        st.caption("No invoices match.")

    if sel_inv is not None:
        with st.container(border=True):
            st.markdown(f"##### {sel_inv['number']} — {sel_inv['customer']} "
                        f"· {sel_inv['status']}")
            from bizclinik_erp.models import JournalEntry
            with get_session() as s:
                inv = s.get(SalesInvoice, int(sel_inv["id"]))
                line_rows = [{
                    "description": l.description, "qty": l.qty,
                    "unit_price": l.unit_price, "tax_rate": l.tax_rate,
                    "subtotal": l.subtotal,
                } for l in inv.lines]
                rct_rows = [{
                    "number": r.number, "date": r.receipt_date,
                    "amount": r.amount, "method": r.method,
                    "status": r.status.value,
                } for r in s.execute(select(Receipt).where(
                    Receipt.invoice_id == inv.id)).scalars()]
                je = s.get(JournalEntry, inv.je_id) if inv.je_id else None
                je_no = je.entry_no if je else None
            ui.dataframe(pd.DataFrame(line_rows), hide_index=True,
                         width="stretch",
                         column_config={"unit_price": ui.money_col("unit_price"),
                                        "subtotal": ui.money_col("subtotal")})
            dc1, dc2 = st.columns([2, 1])
            with dc1:
                if rct_rows:
                    st.markdown("**Receipts applied**")
                    ui.dataframe(pd.DataFrame(rct_rows), hide_index=True,
                                 width="stretch",
                                 column_config={"amount": ui.money_col("amount")})
                else:
                    st.caption("No receipts applied yet.")
                if je_no:
                    st.caption(f"Posted as journal **{je_no}**.")
            with dc2:
                if st.button("📄 Generate PDF", key="pdf_btn",
                             use_container_width=True):
                    with get_session() as s:
                        tmpdir = Path(tempfile.mkdtemp(prefix="bizclinik_pdf_"))
                        out = tmpdir / f"{sel_inv['number'].replace('/', '_')}.pdf"
                        write_invoice_pdf(s, int(sel_inv["id"]), out)
                    st.download_button("⬇ Download invoice PDF",
                                       data=out.read_bytes(),
                                       file_name=out.name,
                                       mime="application/pdf",
                                       use_container_width=True)
    else:
        st.caption("Select an invoice to see its lines, receipts and PDF.")

    st.divider()
    st.subheader("New invoice")
    with get_session() as s:
        cust_opts = _customer_options(s)
        prods = _product_options(s)
    if not cust_opts:
        st.info("No customers yet.")
        st.page_link("views/17_Settings.py", label="➕ Add your first customer in Settings", icon="⚙️")
    else:
        with get_session() as s:
            from bizclinik_erp.models import Currency
            from sqlalchemy import select as _sel
            cur_codes = [c.code for c in s.execute(
                _sel(Currency).where(Currency.is_active == True)  # noqa: E712
                .order_by(Currency.is_base.desc(), Currency.code)).scalars()]
        with st.form("new_invoice"):
            sel_cust = st.selectbox("Customer", list(cust_opts.keys()))
            c1, c2, c3 = st.columns(3)
            inv_date = c1.date_input("Invoice date", value=date.today())
            due = c2.date_input("Due date", value=date.today() + timedelta(days=30))
            sel_cur = c3.selectbox("Currency", cur_codes or ["NGN"],
                                    help="Foreign-currency invoices post to the "
                                         "ledger in NGN at the latest rate.")
            prod_by_label = {f"{p['sku']} — {p['name']}": p for p in prods}
            seed = [{"product": "(none)", "description": "", "qty": 1.0,
                     "unit_price": 0.0, "tax_rate": 0.075}]
            grid = st.data_editor(pd.DataFrame(seed), num_rows="dynamic",
                                  key="inv_grid",
                                  column_config={
                                      "product": st.column_config.SelectboxColumn(
                                          "Product",
                                          options=["(none)"] + list(prod_by_label),
                                          help="Pick a product, or leave (none) "
                                               "for a free-text line"),
                                      "description": st.column_config.TextColumn(
                                          "Description", width="large"),
                                      "qty": st.column_config.NumberColumn("Qty", min_value=0.0),
                                      "unit_price": st.column_config.NumberColumn(
                                          "Unit price (₦)", min_value=0.0, format="%.2f",
                                          help="0 with a product selected = use its list price"),
                                      "tax_rate": st.column_config.NumberColumn(
                                          "Tax (decimal)", min_value=0.0, max_value=1.0,
                                          format="%.3f"),
                                  })
            notes = st.text_area("Notes")
            submit = st.form_submit_button("Issue invoice", type="primary")
        if submit:
            lines = []
            for _, row in grid.iterrows():
                prod = prod_by_label.get(str(row.get("product") or ""))
                desc = str(row.get("description") or "").strip()
                if not desc and prod:
                    desc = prod["name"]
                if not desc:
                    continue
                price = float(row["unit_price"] or 0)
                if price == 0 and prod:
                    price = float(prod["price"] or 0)
                lines.append(sales_svc.LineInput(
                    product_id=prod["id"] if prod else None,
                    description=desc, qty=float(row["qty"] or 0),
                    unit_price=price,
                    tax_rate=float(row["tax_rate"] or 0),
                ))
            if not lines:
                st.error("Add at least one line.")
            else:
                try:
                    with get_session() as s:
                        inv = sales_svc.issue_invoice(
                            s, customer_id=cust_opts[sel_cust], invoice_date=inv_date,
                            due_date=due, lines=lines, notes=notes or None,
                            currency_code=sel_cur,
                        )
                        cur = inv.currency_code
                        st.success(f"Issued {inv.number} — total {cur} "
                                   f"{inv.grand_total:,.2f}"
                                   + (f" (₦{inv.grand_total * inv.fx_rate:,.2f})"
                                      if cur != "NGN" else ""))
                except ValueError as e:
                    st.error(str(e))


# ----- Quotations tab -------------------------------------------------------


with tab_quote:
    st.subheader("Quotations")
    with get_session() as s:
        quos = s.execute(select(Quotation).order_by(Quotation.issue_date.desc())).scalars().all()
        rows = [{
            "number": q.number, "date": q.issue_date,
            "customer": q.customer.name if q.customer else "",
            "total": q.grand_total, "status": q.status.value,
        } for q in quos]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("New quotation")
    with get_session() as s:
        cust_opts = _customer_options(s)
        prods = _product_options(s)
    if cust_opts:
        with st.form("new_quote"):
            sel_cust = st.selectbox("Customer", list(cust_opts.keys()), key="quo_cust")
            issue = st.date_input("Issue date", value=date.today(), key="quo_issue")
            valid = st.date_input("Valid until",
                                   value=date.today() + timedelta(days=30), key="quo_valid")
            seed = [{"product_id": p["id"], "description": p["name"], "qty": 1,
                     "unit_price": p["price"], "tax_rate": 0.075}
                    for p in prods[:3]] or [{"product_id": None, "description": "",
                                                "qty": 1, "unit_price": 0.0,
                                                "tax_rate": 0.075}]
            grid = st.data_editor(pd.DataFrame(seed), num_rows="dynamic", key="quo_grid")
            notes = st.text_area("Notes", key="quo_notes")
            submit = st.form_submit_button("Save quotation", type="primary")
        if submit:
            lines = []
            for _, row in grid.iterrows():
                desc = str(row.get("description") or "").strip()
                if not desc:
                    continue
                lines.append(sales_svc.LineInput(
                    product_id=int(row["product_id"]) if pd.notna(row["product_id"]) else None,
                    description=desc, qty=float(row["qty"] or 0),
                    unit_price=float(row["unit_price"] or 0),
                    tax_rate=float(row["tax_rate"] or 0),
                ))
            if not lines:
                st.error("Add at least one line.")
            else:
                with get_session() as s:
                    q = sales_svc.create_quotation(
                        s, customer_id=cust_opts[sel_cust], issue_date=issue,
                        valid_until=valid, lines=lines, notes=notes or None,
                    )
                    st.success(f"Saved {q.number} — total ₦{q.grand_total:,.2f}")


# ----- Sales orders tab -----------------------------------------------------


with tab_so:
    st.subheader("Sales orders")
    with get_session() as s:
        sos = s.execute(select(SalesOrder).order_by(SalesOrder.order_date.desc())).scalars().all()
        rows = [{
            "number": o.number, "date": o.order_date,
            "customer": o.customer.name if o.customer else "",
            "status": o.status.value,
        } for o in sos]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("New sales order")
    with get_session() as s:
        cust_opts = _customer_options(s)
        prods = _product_options(s)
    if not cust_opts:
        st.info("No customers yet.")
        st.page_link("views/17_Settings.py", label="➕ Add a customer in Settings", icon="⚙️")
    else:
        with st.form("new_so"):
            sel_cust = st.selectbox("Customer", list(cust_opts.keys()), key="so_cust")
            order_date = st.date_input("Order date", value=date.today(), key="so_date")
            seed = [{"product_id": p["id"], "description": p["name"], "qty": 1,
                     "unit_price": p["price"], "tax_rate": 0.075}
                    for p in prods[:3]] or [{"product_id": None, "description": "",
                                                "qty": 1, "unit_price": 0.0,
                                                "tax_rate": 0.075}]
            grid = st.data_editor(pd.DataFrame(seed), num_rows="dynamic", key="so_grid")
            notes = st.text_area("Notes", key="so_notes")
            submit = st.form_submit_button("Save sales order", type="primary")
        if submit:
            lines = []
            for _, row in grid.iterrows():
                desc = str(row.get("description") or "").strip()
                if not desc:
                    continue
                lines.append(sales_svc.LineInput(
                    product_id=int(row["product_id"]) if pd.notna(row["product_id"]) else None,
                    description=desc, qty=float(row["qty"] or 0),
                    unit_price=float(row["unit_price"] or 0),
                    tax_rate=float(row["tax_rate"] or 0),
                ))
            if not lines:
                st.error("Add at least one line.")
            else:
                with get_session() as s:
                    so = sales_svc.create_sales_order(
                        s, customer_id=cust_opts[sel_cust], order_date=order_date,
                        lines=lines, notes=notes or None,
                    )
                    st.success(f"Saved {so.number}")


# ----- Receipts tab ---------------------------------------------------------


with tab_rct:
    st.subheader("Receipts")
    with get_session() as s:
        rcts = s.execute(select(Receipt).order_by(Receipt.receipt_date.desc())).scalars().all()
        rows = [{
            "number": r.number, "date": r.receipt_date,
            "customer": r.customer.name if r.customer else "",
            "invoice": r.invoice.number if r.invoice else "",
            "amount": r.amount, "method": r.method,
            "reference": r.reference, "status": r.status.value,
        } for r in rcts]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Record receipt")
    with get_session() as s:
        cust_opts = _customer_options(s)
        bank_opts = _bank_options(s)
        open_invs = s.execute(select(SalesInvoice).where(
            SalesInvoice.status.in_([DocStatus.POSTED, DocStatus.PARTIAL])
        ).order_by(SalesInvoice.invoice_date.desc())).scalars().all()
        inv_opts = {f"{i.number} ({i.customer.name if i.customer else '?'}) — "
                     f"₦{i.outstanding:,.2f} outstanding": i.id
                     for i in open_invs}
    if cust_opts and bank_opts:
        with st.form("new_receipt"):
            sel_cust = st.selectbox("Customer", list(cust_opts.keys()), key="rct_cust")
            sel_inv = st.selectbox("Apply to invoice (optional)",
                                    [""] + list(inv_opts.keys()), key="rct_inv")
            sel_bank = st.selectbox("Bank", list(bank_opts.keys()), key="rct_bank")
            amt = st.number_input("Amount (₦)", min_value=0.0, format="%.2f")
            method = st.selectbox("Method", ["BANK", "CASH", "CARD"])
            ref = st.text_input("Reference")
            rdate = st.date_input("Receipt date", value=date.today())
            submit = st.form_submit_button("Record receipt", type="primary")
        if submit:
            with get_session() as s:
                r = sales_svc.record_receipt(
                    s, customer_id=cust_opts[sel_cust], receipt_date=rdate,
                    amount=amt, bank_account_id=bank_opts[sel_bank],
                    invoice_id=inv_opts.get(sel_inv) if sel_inv else None,
                    method=method, reference=ref or None,
                )
                st.success(f"Recorded {r.number} — ₦{r.amount:,.2f}")

auth.render_logout_in_sidebar()
