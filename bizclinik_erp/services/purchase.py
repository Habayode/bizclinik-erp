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

from .. import authz
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
    currency_code: str = "NGN",
    fx_rate: Optional[float] = None,
) -> Bill:
    """Receive a supplier bill: post to GL and increase stock for stockable lines.

    Multi-currency: bill may be in `currency_code`; GL + inventory valuation
    are posted in NGN at `fx_rate` (NGN per unit, captured at receipt).
    """
    from . import fx as fx_svc

    accts = _resolve_accounts(session)
    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError(f"Supplier {supplier_id} not found.")

    authz.require_perm("post.bill")
    lines = list(lines)
    if not lines:
        raise ValueError("A bill needs at least one line.")

    currency_code = (currency_code or "NGN").upper()
    rate = fx_svc.resolve_rate(session, currency_code, fx_rate=fx_rate,
                                as_of=bill_date)

    def _ngn(amount: float) -> float:
        return round(amount * rate, 2)

    bill = Bill(
        number=next_number(session, "BIL", bill_date),
        bill_date=bill_date, due_date=due_date,
        supplier_id=supplier_id, po_id=po_id, notes=notes,
        status=DocStatus.DRAFT,
        currency_code=currency_code, fx_rate=rate,
    )
    for l in lines:
        bill.lines.append(BillLine(
            product_id=l.product_id, description=l.description,
            qty=l.qty, unit_cost=l.unit_cost, tax_rate=l.tax_rate,
            account_id=l.expense_account_id,
        ))
    session.add(bill)
    session.flush()

    # Group debit side: per inventory/expense account (foreign amounts).
    debit_by_acct: dict[int, float] = {}
    # stock lines: (product, qty, unit_cost_NGN)
    stock_lines: list[tuple[Product, float, float]] = []
    for line in bill.lines:
        line_total = round(line.qty * line.unit_cost, 2)
        if line_total == 0:
            continue
        target_acct: Optional[int] = line.account_id
        if line.product_id and not target_acct:
            prod = session.get(Product, line.product_id)
            if prod and prod.is_stockable:
                target_acct = prod.inventory_account_id or accts["INV"].id
                # Inventory is valued in NGN — convert unit cost at the rate.
                stock_lines.append((prod, line.qty, _ngn(line.unit_cost)))
            elif prod:
                target_acct = prod.income_account_id  # unlikely, fallback below
        if not target_acct:
            target_acct = accts["DEFAULT_EXPENSE"].id
        debit_by_acct[target_acct] = debit_by_acct.get(target_acct, 0.0) + line_total

    je_lines: list[JELine] = []
    for acct_id, amt in debit_by_acct.items():
        je_lines.append(JELine(account_id=acct_id, debit=_ngn(amt),
                                memo=f"Bill {bill.number} from {supplier.name}"))
    if bill.tax_total:
        # Sign-aware: a negative tax total reverses Input VAT with a credit
        # rather than a negative debit (which post_journal rejects).
        tax_ngn = _ngn(bill.tax_total)
        je_lines.append(
            JELine(account_id=accts["VAT_IN"].id, debit=tax_ngn,
                   memo=f"Input VAT — bill {bill.number}")
            if tax_ngn >= 0 else
            JELine(account_id=accts["VAT_IN"].id, credit=-tax_ngn,
                   memo=f"Input VAT (reversal) — bill {bill.number}"))
    ap_acct = supplier.payable_account_id or accts["AP"].id
    je_lines.append(JELine(account_id=ap_acct, credit=_ngn(bill.grand_total),
                            memo=f"AP — {supplier.name}", supplier_id=supplier.id))

    je = post_journal(
        session, bill_date,
        f"Bill {bill.number} from {supplier.name}",
        je_lines, source_kind="BILL", source_id=bill.id,
    )
    bill.je_id = je.id

    # Stock receipts (after JE so any errors abort cleanly) — NGN unit cost.
    for prod, qty, unit_cost_ngn in stock_lines:
        inv_svc.record_stock_in(
            session, prod, qty=qty, unit_cost=unit_cost_ngn, on=bill_date,
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
    settlement_fx_rate: Optional[float] = None,
) -> Payment:
    """Record cash out to a supplier. Posts DR AP / CR Bank (+ realized FX).

    For an NGN bill `amount` is NGN. For a foreign bill, `amount` is in the
    bill's currency; `settlement_fx_rate` (defaults to the bill's issue rate)
    gives the NGN that leaves the bank, and any difference vs the AP booked at
    the issue rate is a realized FX gain/loss.
    """
    from . import fx as fx_svc

    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError(f"Supplier {supplier_id} not found.")
    bank = session.get(BankAccount, bank_account_id)
    if not bank:
        raise ValueError(f"Bank account {bank_account_id} not found.")

    authz.require_perm("post.payment")
    # Idempotency: a repeated (supplier, reference) is a retry/replay, not a new
    # payment. Return the existing one rather than double-posting the cash JE.
    if reference:
        dup = session.execute(
            select(Payment).where(Payment.supplier_id == supplier_id,
                                  Payment.reference == reference)
        ).scalars().first()
        if dup is not None:
            return dup

    accts = _resolve_accounts(session)
    ap_acct = supplier.payable_account_id or accts["AP"].id

    bill = session.get(Bill, bill_id) if bill_id else None
    if bill and amount > bill.outstanding + 0.01:
        raise ValueError(
            f"Payment {amount:,.2f} exceeds the outstanding balance "
            f"{bill.outstanding:,.2f} on {bill.number}. Record the excess as a "
            "separate unapplied payment (supplier advance) instead.")
    issue_rate = bill.fx_rate if bill else 1.0
    settle_rate = settlement_fx_rate if settlement_fx_rate is not None else issue_rate

    ngn_from_bank = round(amount * settle_rate, 2)   # cash actually paid
    ap_cleared = round(amount * issue_rate, 2)       # AP booked at issue rate
    fx_diff = round(ngn_from_bank - ap_cleared, 2)   # paid more (>0) => loss

    payment = Payment(
        number=next_number(session, "PAY", payment_date),
        payment_date=payment_date,
        supplier_id=supplier_id, bill_id=bill_id,
        bank_account_id=bank_account_id,
        amount=ngn_from_bank,
        # Amount applied to the bill, in the BILL's currency (see record_receipt).
        applied_amount=amount,
        method=method, reference=reference,
        status=DocStatus.DRAFT,
    )
    session.add(payment)
    session.flush()

    je_lines = [
        JELine(account_id=ap_acct, debit=ap_cleared,
               memo=f"AP settled — {supplier.name}", supplier_id=supplier.id),
        JELine(account_id=bank.gl_account_id, credit=ngn_from_bank,
               memo=f"Payment to {supplier.name}"),
    ]
    if abs(fx_diff) >= 0.01:
        fx_acct = fx_svc.fx_gainloss_account_id(session)
        if fx_diff > 0:  # paid more NGN than AP booked → loss (debit income acct)
            je_lines.append(JELine(account_id=fx_acct, debit=fx_diff,
                                    memo="Realized FX loss"))
        else:            # paid less → gain (credit income acct)
            je_lines.append(JELine(account_id=fx_acct, credit=-fx_diff,
                                    memo="Realized FX gain"))

    je = post_journal(
        session, payment_date,
        f"Payment {payment.number} to {supplier.name}",
        je_lines, source_kind="PAYMENT", source_id=payment.id,
    )
    payment.je_id = je.id
    payment.status = DocStatus.POSTED

    if bill:
        bill.amount_paid = round(bill.amount_paid + amount, 2)
        if bill.amount_paid + 0.01 >= bill.grand_total:
            bill.status = DocStatus.PAID
        elif bill.amount_paid > 0:
            bill.status = DocStatus.PARTIAL
    session.flush()
    return payment
