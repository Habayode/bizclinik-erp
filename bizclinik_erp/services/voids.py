"""Void/reverse posted documents.

Accountants reverse, they don't delete. Each void:
  1. Posts a reversing JE that exactly negates the original posting.
  2. Flips the source document's status to CANCELLED.
  3. Writes an audit_log row.
  4. Reverses the inventory movement when applicable.

Re-voiding a cancelled document is a no-op (returns the existing reversal).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Bill,
    DocStatus,
    JournalEntry,
    Payment,
    Receipt,
    SalesInvoice,
    StockMovement,
)
from ..models.audit import AuditAction
from .. import authz
from .audit import record
from .ledger import reverse_journal


def _find_je(session: Session, je_id: Optional[int]) -> Optional[JournalEntry]:
    if not je_id:
        return None
    return session.get(JournalEntry, je_id)


def _reverse_stock_movements(session: Session, source_kind: str, source_id: int,
                              on: date, memo: str) -> int:
    """For each StockMovement linked to the source, post an equal-and-opposite
    StockMovement so on-hand and avg-cost roll back cleanly."""
    movements = list(session.execute(
        select(StockMovement).where(
            StockMovement.source_kind == source_kind,
            StockMovement.source_id == source_id,
        )
    ).scalars())
    for mv in movements:
        # Build the reverse: flip qty_in / qty_out and recompute running stock.
        from . import inventory as inv_svc
        product = mv.product
        if mv.qty_in > 0:
            # Original was a stock receipt → reverse by issuing
            inv_svc.record_stock_out(
                session, product, qty=mv.qty_in, on=on,
                unit_cost=mv.unit_cost,
                source_kind=f"VOID_{source_kind}", source_id=source_id,
                memo=memo,
            )
        elif mv.qty_out > 0:
            inv_svc.record_stock_in(
                session, product, qty=mv.qty_out, unit_cost=mv.unit_cost,
                on=on,
                source_kind=f"VOID_{source_kind}", source_id=source_id,
                memo=memo,
            )
    return len(movements)


def void_invoice(session: Session, invoice_id: int, *,
                  reason: str, on: Optional[date] = None,
                  user_id: Optional[int] = None) -> dict:
    authz.require_perm("void.any")
    inv = session.get(SalesInvoice, invoice_id)
    if not inv:
        raise ValueError("Invoice not found.")
    if inv.status == DocStatus.CANCELLED:
        return {"already_cancelled": True, "invoice_id": invoice_id}
    if not reason or len(reason.strip()) < 3:
        raise ValueError("A reason is required to void an invoice.")
    # Cash applied to the invoice must be dealt with first, or the receipts
    # would stay booked against a cancelled sale.
    live_receipts = list(session.execute(
        select(Receipt).where(Receipt.invoice_id == inv.id,
                              Receipt.status != DocStatus.CANCELLED)
    ).scalars())
    if live_receipts:
        nums = ", ".join(r.number for r in live_receipts)
        raise ValueError(
            f"Invoice {inv.number} has {len(live_receipts)} receipt(s) applied "
            f"({nums}). Void the receipt(s) first, then void the invoice.")
    on = on or date.today()
    rev_jes = []
    for je in (_find_je(session, inv.je_id), _find_je(session, inv.cogs_je_id)):
        if je:
            r = reverse_journal(session, je, on,
                                 memo=f"Void invoice {inv.number}: {reason}")
            rev_jes.append(r)
    moved = _reverse_stock_movements(session, "INVOICE", inv.id, on,
                                      f"Void invoice {inv.number}: {reason}")
    inv.status = DocStatus.CANCELLED
    record(session, action=AuditAction.VOID, entity_type="sales_invoice",
           entity_id=inv.id,
           description=f"Voided invoice {inv.number}: {reason}",
           payload={"reversing_je_nos": [r.entry_no for r in rev_jes],
                    "stock_movements_reversed": moved},
           user_id=user_id, source="services.voids")
    return {"invoice_id": invoice_id,
            "reversing_je_nos": [r.entry_no for r in rev_jes],
            "stock_movements_reversed": moved}


def void_bill(session: Session, bill_id: int, *,
                reason: str, on: Optional[date] = None,
                user_id: Optional[int] = None) -> dict:
    authz.require_perm("void.any")
    bill = session.get(Bill, bill_id)
    if not bill:
        raise ValueError("Bill not found.")
    if bill.status == DocStatus.CANCELLED:
        return {"already_cancelled": True, "bill_id": bill_id}
    if not reason or len(reason.strip()) < 3:
        raise ValueError("A reason is required to void a bill.")
    # Cash applied to the bill must be dealt with first, or the payments would
    # stay booked against a cancelled purchase.
    live_payments = list(session.execute(
        select(Payment).where(Payment.bill_id == bill.id,
                              Payment.status != DocStatus.CANCELLED)
    ).scalars())
    if live_payments:
        nums = ", ".join(p.number for p in live_payments)
        raise ValueError(
            f"Bill {bill.number} has {len(live_payments)} payment(s) applied "
            f"({nums}). Void the payment(s) first, then void the bill.")
    on = on or date.today()
    rev_jes = []
    je = _find_je(session, bill.je_id)
    if je:
        rev_jes.append(reverse_journal(session, je, on,
                                        memo=f"Void bill {bill.number}: {reason}"))
    moved = _reverse_stock_movements(session, "BILL", bill.id, on,
                                      f"Void bill {bill.number}: {reason}")
    bill.status = DocStatus.CANCELLED
    record(session, action=AuditAction.VOID, entity_type="bill",
           entity_id=bill.id,
           description=f"Voided bill {bill.number}: {reason}",
           payload={"reversing_je_nos": [r.entry_no for r in rev_jes],
                    "stock_movements_reversed": moved},
           user_id=user_id, source="services.voids")
    return {"bill_id": bill_id,
            "reversing_je_nos": [r.entry_no for r in rev_jes],
            "stock_movements_reversed": moved}


def void_receipt(session: Session, receipt_id: int, *,
                  reason: str, on: Optional[date] = None,
                  user_id: Optional[int] = None) -> dict:
    authz.require_perm("void.any")
    rct = session.get(Receipt, receipt_id)
    if not rct:
        raise ValueError("Receipt not found.")
    if rct.status == DocStatus.CANCELLED:
        return {"already_cancelled": True, "receipt_id": receipt_id}
    on = on or date.today()
    je = _find_je(session, rct.je_id)
    rev_entry = None
    if je:
        rev_entry = reverse_journal(session, je, on,
                                     memo=f"Void receipt {rct.number}: {reason}")
    # Refund the invoice's amount_paid.
    if rct.invoice_id:
        inv = session.get(SalesInvoice, rct.invoice_id)
        if inv:
            # Reverse by the invoice-currency amount applied (not the NGN cash
            # figure rct.amount), so foreign-currency invoices don't corrupt
            # amount_paid. Legacy receipts (applied_amount 0) fall back to amount
            # — exact for NGN, which is all historical data.
            applied = rct.applied_amount or rct.amount
            inv.amount_paid = round(inv.amount_paid - applied, 2)
            if inv.status != DocStatus.CANCELLED:
                if inv.amount_paid + 0.01 >= inv.grand_total:
                    inv.status = DocStatus.PAID
                elif inv.amount_paid > 0:
                    inv.status = DocStatus.PARTIAL
                else:
                    inv.status = DocStatus.POSTED
    rct.status = DocStatus.CANCELLED
    record(session, action=AuditAction.VOID, entity_type="receipt",
           entity_id=rct.id, description=f"Voided receipt {rct.number}: {reason}",
           payload={"reversing_je_no": rev_entry.entry_no if rev_entry else None},
           user_id=user_id, source="services.voids")
    return {"receipt_id": receipt_id,
            "reversing_je_no": rev_entry.entry_no if rev_entry else None}


def void_payment(session: Session, payment_id: int, *,
                  reason: str, on: Optional[date] = None,
                  user_id: Optional[int] = None) -> dict:
    authz.require_perm("void.any")
    pay = session.get(Payment, payment_id)
    if not pay:
        raise ValueError("Payment not found.")
    if pay.status == DocStatus.CANCELLED:
        return {"already_cancelled": True, "payment_id": payment_id}
    on = on or date.today()
    je = _find_je(session, pay.je_id)
    rev_entry = None
    if je:
        rev_entry = reverse_journal(session, je, on,
                                     memo=f"Void payment {pay.number}: {reason}")
    if pay.bill_id:
        bill = session.get(Bill, pay.bill_id)
        if bill:
            # Reverse by the bill-currency amount applied (see void_receipt).
            applied = pay.applied_amount or pay.amount
            bill.amount_paid = round(bill.amount_paid - applied, 2)
            if bill.status != DocStatus.CANCELLED:
                if bill.amount_paid + 0.01 >= bill.grand_total:
                    bill.status = DocStatus.PAID
                elif bill.amount_paid > 0:
                    bill.status = DocStatus.PARTIAL
                else:
                    bill.status = DocStatus.POSTED
    pay.status = DocStatus.CANCELLED
    record(session, action=AuditAction.VOID, entity_type="payment",
           entity_id=pay.id, description=f"Voided payment {pay.number}: {reason}",
           payload={"reversing_je_no": rev_entry.entry_no if rev_entry else None},
           user_id=user_id, source="services.voids")
    return {"payment_id": payment_id,
            "reversing_je_no": rev_entry.entry_no if rev_entry else None}
