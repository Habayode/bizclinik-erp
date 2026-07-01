"""Point-of-Sale service for the Retail edition (Supermarket / FMCG).

A retail sale is a walk-in cash/card transaction. One call rings it up: it posts
the full double-entry via the existing sales engine — revenue, output VAT, COGS
and an inventory reduction — and settles the payment immediately. POS is just a
fast front-end over issue_invoice + record_receipt, so the ledger, stock and tax
all stay correct.

    checkout() = issue_invoice (DR AR / CR Sales + Output VAT; DR COGS / CR
                 Inventory + stock-out) then record_receipt (DR Till / CR AR).
    Net effect of a cash sale: DR Till, CR Sales, CR Output VAT, DR COGS,
                 CR Inventory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import authz
from ..models import Customer, Product
from .sales import LineInput, issue_invoice, record_receipt

_WALKIN_CODE = "WALK-IN"
_DEFAULT_VAT = 0.075


@dataclass
class CartLine:
    product_id: int
    qty: float = 1.0
    unit_price: Optional[float] = None   # override; else the product's list price
    tax_rate: Optional[float] = None     # override; else the product's tax / 7.5%
    discount_pct: float = 0.0            # 0..1 line discount off the price


def walkin_customer(session: Session) -> Customer:
    """Get-or-create the shared walk-in customer used for anonymous POS sales."""
    c = session.execute(
        select(Customer).where(Customer.code == _WALKIN_CODE)
    ).scalar_one_or_none()
    if c is None:
        c = Customer(code=_WALKIN_CODE, name="Walk-in customer")
        session.add(c)
        session.flush()
    return c


def find_product(session: Session, code: str) -> Optional[Product]:
    """Resolve a scanned/typed code to an active product — barcode first, then
    SKU. Returns None if nothing matches."""
    code = (code or "").strip()
    if not code:
        return None
    p = session.execute(
        select(Product).where(Product.barcode == code,
                              Product.is_active == True)  # noqa: E712
    ).scalars().first()
    if p is None:
        p = session.execute(
            select(Product).where(Product.sku == code,
                                  Product.is_active == True)  # noqa: E712
        ).scalars().first()
    return p


def _resolve_line(session: Session, cl: CartLine) -> LineInput:
    prod = session.get(Product, cl.product_id)
    if prod is None:
        raise ValueError(f"Product {cl.product_id} not found.")
    if cl.qty <= 0:
        raise ValueError(f"Quantity for {prod.name} must be positive.")
    price = (cl.unit_price if cl.unit_price is not None
             else float(prod.standard_price or 0.0))
    disc = max(0.0, min(1.0, float(cl.discount_pct or 0.0)))
    if disc:
        price = round(price * (1 - disc), 2)
    if cl.tax_rate is not None:
        tax = cl.tax_rate
    elif prod.tax_code is not None:
        tax = float(prod.tax_code.rate or 0.0)
    else:
        tax = _DEFAULT_VAT
    return LineInput(product_id=prod.id, description=prod.name, qty=float(cl.qty),
                     unit_price=price, tax_rate=tax)


def checkout(session: Session, *, lines: list[CartLine], bank_account_id: int,
             method: str = "CASH", customer_id: Optional[int] = None,
             tendered: Optional[float] = None, on: Optional[date] = None,
             reference: Optional[str] = None) -> dict:
    """Ring up a sale: issue the invoice (revenue + VAT + COGS + stock-out) and
    record full payment in one atomic step. Returns a receipt summary."""
    authz.require_perm("post.invoice")
    if not lines:
        raise ValueError("Cart is empty.")
    on = on or date.today()
    cust_id = customer_id or walkin_customer(session).id
    line_inputs = [_resolve_line(session, cl) for cl in lines]

    inv = issue_invoice(session, customer_id=cust_id, invoice_date=on,
                        lines=line_inputs, notes=f"POS sale ({method})")
    total = round(inv.grand_total, 2)
    record_receipt(session, customer_id=cust_id, receipt_date=on, amount=total,
                   bank_account_id=bank_account_id, invoice_id=inv.id,
                   method=method, reference=reference)

    subtotal = round(sum(li.qty * li.unit_price for li in line_inputs), 2)
    tax = round(sum(li.qty * li.unit_price * li.tax_rate for li in line_inputs), 2)
    change = (round(tendered - total, 2)
              if (tendered is not None and method == "CASH") else 0.0)
    return {
        "invoice_id": inv.id, "invoice_number": inv.number,
        "subtotal": subtotal, "tax": tax, "total": total,
        "tendered": tendered, "change": max(change, 0.0),
        "items": len(line_inputs), "method": method,
        "lines": [{"name": li.description, "qty": li.qty, "price": li.unit_price,
                   "line_total": round(li.qty * li.unit_price * (1 + li.tax_rate), 2)}
                  for li in line_inputs],
    }
