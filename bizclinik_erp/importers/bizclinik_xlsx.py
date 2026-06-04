"""Import a BizClinik accounting workbook into the ERP database.

Reads the legacy Wendysrack-style xlsx (Company Details, Inventory List,
Supplier Module, Customer Module, Operating Module, Chart of Accounts) and:

  1. Updates / inserts Company, Customer, Supplier, Product master records
  2. Posts opening journal entries for each transaction row, in date order:
     - Supplier rows → Bill (creates AP + stock + input VAT)
     - Customer rows → Invoice (creates AR + revenue + COGS + stock-out)
     - Operating rows → Bill with non-stock expense account
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

# Use the vendored wrapper at bizclinik_erp/_legacy_bizclinik so the ERP is
# self-contained (no sibling-path dependency on bizclinik-wrapper).
from .._legacy_bizclinik import BizClinikWorkbook  # noqa: E402
from .._legacy_bizclinik.models import (  # noqa: E402
    CustomerEntry as XlsxCustomerEntry,
    InventoryItem as XlsxInventoryItem,
    OperatingEntry as XlsxOperatingEntry,
    SupplierEntry as XlsxSupplierEntry,
)

from ..models import (  # noqa: E402
    Account,
    Company,
    Customer,
    Product,
    Supplier,
)
from ..services import purchase, sales  # noqa: E402
from ..services.seed import seed_defaults  # noqa: E402


_MAX_CODE_LEN = 32  # match the model column width


def _safe_code(raw: Optional[str], fallback: str) -> str:
    s = (raw or "").strip()
    if not s:
        s = fallback
    # SKUs in the workbook may contain spaces; collapse to underscore-safe form.
    s = s.replace(" ", "_")
    return s[:_MAX_CODE_LEN]


def _txn_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    # Fallback to a deterministic date so the GL still posts.
    return date(2026, 1, 1)


def _seed_company(session: Session, wb: BizClinikWorkbook) -> Company:
    info = wb.company()
    company = session.execute(select(Company)).scalar_one_or_none()
    if not company:
        company = Company(name=info.name or "(unnamed)")
        session.add(company)
    company.rc_number = info.rc_number
    company.address = info.address
    company.email = info.email
    company.phone = info.phone
    company.vat_number = info.vat_no
    session.flush()
    return company


def _seed_products(session: Session, wb: BizClinikWorkbook) -> dict[str, Product]:
    """Insert any inventory-list items + any codes mentioned in customer/supplier rows."""
    accts_by_code = {a.code: a for a in session.execute(select(Account)).scalars()}
    inv_acct = accts_by_code.get("1140")
    rev_acct = accts_by_code.get("4100")
    cogs_acct = accts_by_code.get("5100")

    products: dict[str, Product] = {}
    # Existing
    for p in session.execute(select(Product)).scalars():
        products[p.sku] = p

    def _ensure(code: str, description: Optional[str] = None) -> Product:
        sku = _safe_code(code, "UNKNOWN")
        if sku in products:
            return products[sku]
        prod = Product(
            sku=sku,
            name=(description or sku)[:255],
            is_stockable=True,
            inventory_account_id=inv_acct.id if inv_acct else None,
            income_account_id=rev_acct.id if rev_acct else None,
            cogs_account_id=cogs_acct.id if cogs_acct else None,
        )
        session.add(prod)
        session.flush()
        products[sku] = prod
        return prod

    # From master inventory list
    for it in wb.inventory_items():
        if it.code:
            _ensure(it.code, it.description)
    # From transactional sheets — may add codes the inventory list missed.
    for e in wb.supplier_entries():
        if e.code:
            _ensure(e.code, e.description)
    for e in wb.customer_entries():
        if e.code:
            _ensure(e.code, e.description)
    return products


def _seed_customers(session: Session, wb: BizClinikWorkbook) -> dict[str, Customer]:
    existing = {c.code: c for c in session.execute(select(Customer)).scalars()}
    seen: dict[str, Customer] = dict(existing)
    counter = len(existing) + 1
    for e in wb.customer_entries():
        name = (e.customer or "").strip()
        if not name:
            continue
        key = name.lower()
        # Map by lower-name → existing customer, else create
        match = next((c for c in seen.values() if c.name.lower() == key), None)
        if match:
            continue
        code = _safe_code(name[:8].upper(), f"C{counter:04d}")
        while code in seen:
            counter += 1
            code = f"C{counter:04d}"
        cust = Customer(code=code, name=name)
        session.add(cust)
        session.flush()
        seen[code] = cust
        counter += 1
    return seen


def _seed_suppliers(session: Session, wb: BizClinikWorkbook) -> dict[str, Supplier]:
    existing = {sup.code: sup for sup in session.execute(select(Supplier)).scalars()}
    seen: dict[str, Supplier] = dict(existing)
    counter = len(existing) + 1
    for e in list(wb.supplier_entries()) + list(wb.operating_entries()):
        name = (getattr(e, "vendor", None) or "").strip()
        if not name:
            continue
        key = name.lower()
        match = next((s for s in seen.values() if s.name.lower() == key), None)
        if match:
            continue
        code = _safe_code(name[:8].upper(), f"S{counter:04d}")
        while code in seen:
            counter += 1
            code = f"S{counter:04d}"
        sup = Supplier(code=code, name=name)
        session.add(sup)
        session.flush()
        seen[code] = sup
        counter += 1
    return seen


def _find_customer(session: Session, name: str) -> Optional[Customer]:
    if not name:
        return None
    return session.execute(
        select(Customer).where(Customer.name == name)
    ).scalar_one_or_none() or session.execute(
        select(Customer).where(Customer.name.ilike(name))
    ).scalar_one_or_none()


def _find_supplier(session: Session, name: str) -> Optional[Supplier]:
    if not name:
        return None
    return session.execute(
        select(Supplier).where(Supplier.name == name)
    ).scalar_one_or_none() or session.execute(
        select(Supplier).where(Supplier.name.ilike(name))
    ).scalar_one_or_none()


def _find_product(session: Session, code: Optional[str]) -> Optional[Product]:
    if not code:
        return None
    sku = _safe_code(code, "")
    if not sku:
        return None
    return session.execute(select(Product).where(Product.sku == sku)).scalar_one_or_none()


def _expense_account_for_description(session: Session, desc: str) -> Account:
    """Map an operating-module description to a default expense account."""
    d = (desc or "").lower()
    mapping = [
        (("salary", "wages", "payroll"), "6100"),
        (("rent", "utility", "utilities", "electricity", "water"), "6200"),
        (("fuel", "diesel", "petrol"), "6300"),
        (("market", "ad", "advert", "branding", "promo", "sponsor"), "6400"),
        (("bank",), "6500"),
        (("depreciat",), "6600"),
    ]
    for needles, code in mapping:
        if any(n in d for n in needles):
            a = session.execute(select(Account).where(Account.code == code)).scalar_one_or_none()
            if a:
                return a
    return session.execute(select(Account).where(Account.code == "6900")).scalar_one()


def import_workbook(
    session: Session, xlsx_path: str | Path, *,
    fallback_due_days: int = 30,
) -> dict:
    """Import the BizClinik workbook into the ERP. Returns a summary."""
    seed_defaults(session)
    wb = BizClinikWorkbook(xlsx_path, read_only=True)

    company = _seed_company(session, wb)
    products = _seed_products(session, wb)
    customers = _seed_customers(session, wb)
    suppliers = _seed_suppliers(session, wb)

    summary = {
        "company": company.name,
        "products": len(products),
        "customers": len(customers),
        "suppliers": len(suppliers),
        "bills_posted": 0,
        "invoices_posted": 0,
        "opex_bills_posted": 0,
        "skipped": [],
    }

    # Post supplier entries first (stock-in must precede sales of that stock).
    sup_rows = [e for e in wb.supplier_entries()
                 if (e.vendor or "").strip() and (e.code or "").strip()]
    sup_rows.sort(key=lambda e: _txn_date(e.date))
    for e in sup_rows:
        supplier = _find_supplier(session, e.vendor)
        product = _find_product(session, e.code)
        if not supplier or not product:
            summary["skipped"].append({"kind": "supplier",
                                        "reason": "missing supplier or product",
                                        "row": str(e.to_dict())})
            continue
        qty = float(e.qty_in or 0)
        rate = float(e.rate or 0)
        if qty <= 0 or rate <= 0:
            summary["skipped"].append({"kind": "supplier",
                                        "reason": "missing qty or rate",
                                        "row": str(e.to_dict())})
            continue
        tax_rate = (float(e.vat or 0) / (qty * rate)) if (e.vat and qty * rate) else 0.0
        bill_date = _txn_date(e.date)
        purchase.receive_bill(
            session, supplier_id=supplier.id, bill_date=bill_date,
            lines=[purchase.POLineInput(
                product_id=product.id, description=product.name,
                qty=qty, unit_cost=rate, tax_rate=tax_rate,
            )],
        )
        summary["bills_posted"] += 1

    # Customer entries → invoices.
    cust_rows = [e for e in wb.customer_entries()
                  if (e.customer or "").strip() and (e.code or "").strip()]
    cust_rows.sort(key=lambda e: _txn_date(e.date))
    for e in cust_rows:
        customer = _find_customer(session, e.customer)
        product = _find_product(session, e.code)
        if not customer or not product:
            summary["skipped"].append({"kind": "customer",
                                        "reason": "missing customer or product",
                                        "row": str(e.to_dict())})
            continue
        qty = float(e.qty_out or 0)
        rate = float(e.rate or 0)
        if qty <= 0 or rate <= 0:
            summary["skipped"].append({"kind": "customer",
                                        "reason": "missing qty or rate",
                                        "row": str(e.to_dict())})
            continue
        tax_rate = (float(e.vat or 0) / (qty * rate)) if (e.vat and qty * rate) else 0.0
        inv_date = _txn_date(e.date)
        sales.issue_invoice(
            session, customer_id=customer.id, invoice_date=inv_date,
            due_date=date.fromordinal(inv_date.toordinal() + fallback_due_days),
            lines=[sales.LineInput(
                product_id=product.id, description=product.name,
                qty=qty, unit_price=rate, tax_rate=tax_rate,
            )],
        )
        summary["invoices_posted"] += 1

    # Operating expenses → bills posted to expense accounts (non-stockable).
    op_rows = [e for e in wb.operating_entries() if (e.vendor or "").strip()]
    op_rows.sort(key=lambda e: _txn_date(e.date))
    for e in op_rows:
        supplier = _find_supplier(session, e.vendor)
        if not supplier:
            summary["skipped"].append({"kind": "operating",
                                        "reason": "missing supplier",
                                        "row": str(e.to_dict())})
            continue
        qty = float(e.qty_in or 1) or 1.0
        rate = float(e.rate or 0)
        total = float(e.total or 0) or (qty * rate)
        if total <= 0:
            summary["skipped"].append({"kind": "operating",
                                        "reason": "missing amount",
                                        "row": str(e.to_dict())})
            continue
        expense_acct = _expense_account_for_description(session, e.description or "")
        tax_rate = (float(e.vat or 0) / total) if (e.vat and total) else 0.0
        bill_date = _txn_date(e.date)
        # Build a single-line bill mapped to the right expense account.
        unit_cost = total / qty if qty else total
        purchase.receive_bill(
            session, supplier_id=supplier.id, bill_date=bill_date,
            lines=[purchase.POLineInput(
                product_id=None, description=e.description or "Operating expense",
                qty=qty, unit_cost=unit_cost, tax_rate=tax_rate,
                expense_account_id=expense_acct.id,
            )],
        )
        summary["opex_bills_posted"] += 1

    return summary
