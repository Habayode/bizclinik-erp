"""Purchase cycle: PO → Bill → Payment.

Bill posts:
    DR Inventory (or expense account)   subtotal
    DR Input VAT                        tax_total
        CR Accounts Payable             grand_total
Plus a StockMovement increasing on-hand at unit_cost (updates avg cost).

Payment posts:
    DR Accounts Payable                 amount
        CR Bank                         amount
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    BankAccount,
    Bill,
    BillLine,
    DocStatus,
    Payment,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from . import inventory as inv_svc
from .ledger import JELine, post_journal
from .numbering import next_number


@dataclass
class POLineInput:
    product_id: Optional[int]
    description: str
    qty: float
    unit_cost: float
    tax_rate: float = 0.0
    expense_account_id: Optional[int] = None  # for non-stock lines


def _resolve_accounts(session: Session) -> dict[str, Account]:
    codes = {"AP": "2110", "INV": "1140", "VAT_IN": "1150",
             "DEFAULT_EXPENSE": "6900"}
    accts: dict[str, Account] = {}
    for k, code in codes.items():
        a = session.execute(select(Account).where(Account.code == code)).scalar_one_or_none()
        if not a:
            raise RuntimeError(f"Default account {code} ({k}) missing. Seed defaults first.")
        accts[k] = a
    return accts


def create_purchase_order(
    session: Session, *, supplier_id: int, order_date: date,
    lines: Iterable[POLineInput], notes: Optional[str] = None,
) -> PurchaseOrder:
    po = PurchaseOrder(
        number=next_number(session, "PO", order_date),
        order_date=order_date,
        supplier_id=supplier_id,
        notes=notes,
        status=DocStatus.DRAFT,
    )
    for l in lines:
        po.lines.append(PurchaseOrderLine(
            product_id=l.product_id, description=l.description,
            qty=l.qty, unit_cost=l.unit_cost, tax_rate=l.tax_rate,
        ))
    session.add(po)
    session.flush()
    return po


def receive_bill(
    session: Session, *, supplier_id: int, bill_date: date,
    lines: Iterable[POLineInput],
    due_date: Optional[date] = None,
    po_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Bill:
    """Receive a supplier bill: post to GL and increase stock for stockable lines."""
    accts = _resolve_accounts(session)
    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError(f"Supplier {supplier_id} not found.")

    bill = Bill(
        number=next_number(session, "BIL", bill_date),
        bill_date=bill_date, due_date=due_date,
        supplier_id=supplier_id, po_id=po_id, notes=notes,
        status=DocStatus.DRAFT,
    )
    for l in lines:
        bill.lines.append(BillLine(
            product_id=l.product_id, description=l.description,
            qty=l.qty, unit_cost=l.unit_cost, tax_rate=l.tax_rate,
            account_id=l.expense_account_id,
        ))
    session.add(bill)
    session.flush()

    # Group debit side: per inventory/expense account
    debit_by_acct: dict[int, float] = {}
    stock_lines: list[tuple[Product, float, float]] = []  # (product, qty, unit_cost)
    for line in bill.lines:
        line_total = round(line.qty * line.unit_cost, 2)
        if line_total == 0:
            continue
        target_acct: Optional[int] = line.account_id
        if line.product_id and not target_acct:
            prod = session.get(Product, line.product_id)
            if prod and prod.is_stockable:
                target_acct = prod.inventory_account_id or accts["INV"].id
                stock_lines.append((prod, line.qty, line.unit_cost))
            elif prod:
                target_acct = prod.income_account_id  # unlikely, fallback below
        if not target_acct:
            target_acct = accts["DEFAULT_EXPENSE"].id
        debit_by_acct[target_acct] = debit_by_acct.get(target_acct, 0.0) + line_total

    je_lines: list[JELine] = []
    for acct_id, amt in debit_by_acct.items():
        je_lines.append(JELine(account_id=acct_id, debit=amt,
                                memo=f"Bill {bill.number} from {supplier.name}"))
    if bill.tax_total:
        je_lines.append(JELine(account_id=accts["VAT_IN"].id, debit=bill.tax_total,
                                memo=f"Input VAT — bill {bill.number}"))
    ap_acct = supplier.payable_account_id or accts["AP"].id
    je_lines.append(JELine(account_id=ap_acct, credit=bill.grand_total,
                            memo=f"AP — {supplier.name}", supplier_id=supplier.id))

    je = post_journal(
        session, bill_date,
        f"Bill {bill.number} from {supplier.name}",
        je_lines, source_kind="BILL", source_id=bill.id,
    )
    bill.je_id = je.id

    # Stock receipts (after JE so any errors abort cleanly).
    for prod, qty, unit_cost in stock_lines:
        inv_svc.record_stock_in(
            session, prod, qty=qty, unit_cost=unit_cost, on=bill_date,
            source_kind="BILL", source_id=bill.id,
            memo=f"Stock received — bill {bill.number}",
        )

    bill.status = DocStatus.POSTED
    session.flush()
    return bill


def record_payment(
    session: Session, *, supplier_id: int, payment_date: date,
    amount: float, bank_account_id: int,
    bill_id: Optional[int] = None,
    method: str = "BANK", reference: Optional[str] = None,
) -> Payment:
    """Record cash out to a supplier. Posts DR AP / CR Bank."""
    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError(f"Supplier {supplier_id} not found.")
    bank = session.get(BankAccount, bank_account_id)
    if not bank:
        raise ValueError(f"Bank account {bank_account_id} not found.")

    accts = _resolve_accounts(session)
    ap_acct = supplier.payable_account_id or accts["AP"].id

    payment = Payment(
        number=next_number(session, "PAY", payment_date),
        payment_date=payment_date,
        supplier_id=supplier_id, bill_id=bill_id,
        bank_account_id=bank_account_id,
        amount=round(amount, 2),
        method=method, reference=reference,
        status=DocStatus.DRAFT,
    )
    session.add(payment)
    session.flush()

    je = post_journal(
        session, payment_date,
        f"Payment {payment.number} to {supplier.name}",
        [
            JELine(account_id=ap_acct, debit=payment.amount,
                   memo=f"AP settled — {supplier.name}", supplier_id=supplier.id),
            JELine(account_id=bank.gl_account_id, credit=payment.amount,
                   memo=f"Payment to {supplier.name}"),
        ],
        source_kind="PAYMENT", source_id=payment.id,
    )
    payment.je_id = je.id
    payment.status = DocStatus.POSTED

    if bill_id:
        bill = session.get(Bill, bill_id)
        if bill:
            bill.amount_paid = round(bill.amount_paid + payment.amount, 2)
            if bill.amount_paid + 0.01 >= bill.grand_total:
                bill.status = DocStatus.PAID
            elif bill.amount_paid > 0:
                bill.status = DocStatus.PARTIAL
    session.flush()
    return payment
