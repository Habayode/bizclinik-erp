"""Sales cycle: Quotation → SalesOrder → SalesInvoice → Receipt.

Each step is a function — the data objects live in models.txn. State is
tracked via DocStatus on each document. GL impact only happens at
issue_invoice() and record_receipt(); quotations and orders are
operational documents with no ledger effect.
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
    Customer,
    DocStatus,
    Product,
    Quotation,
    QuotationLine,
    Receipt,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    StockMovement,
)
from . import inventory as inv_svc
from .ledger import JELine, post_journal
from .numbering import next_number


# ---- inputs ---------------------------------------------------------------


@dataclass
class LineInput:
    product_id: Optional[int]
    description: str
    qty: float
    unit_price: float
    tax_rate: float = 0.0


def _resolve_accounts(session: Session) -> dict[str, Account]:
    """Look up the default AR, Revenue, Output VAT, COGS, Inventory accounts."""
    codes = {"AR": "1130", "REV": "4100", "VAT_OUT": "2120",
             "COGS": "5100", "INV": "1140"}
    accts: dict[str, Account] = {}
    for k, code in codes.items():
        acct = session.execute(
            select(Account).where(Account.code == code)
        ).scalar_one_or_none()
        if not acct:
            raise RuntimeError(f"Default account {code} ({k}) missing. Seed defaults first.")
        accts[k] = acct
    return accts


# ---- quotation ------------------------------------------------------------


def create_quotation(
    session: Session, *, customer_id: int, issue_date: date,
    lines: Iterable[LineInput], valid_until: Optional[date] = None,
    notes: Optional[str] = None,
) -> Quotation:
    quo = Quotation(
        number=next_number(session, "QUO", issue_date),
        issue_date=issue_date,
        valid_until=valid_until,
        customer_id=customer_id,
        notes=notes,
        status=DocStatus.DRAFT,
    )
    for l in lines:
        quo.lines.append(QuotationLine(
            product_id=l.product_id, description=l.description,
            qty=l.qty, unit_price=l.unit_price, tax_rate=l.tax_rate,
        ))
    session.add(quo)
    session.flush()
    return quo


def create_sales_order(
    session: Session, *, customer_id: int, order_date: date,
    lines: Iterable[LineInput], notes: Optional[str] = None,
    quotation_id: Optional[int] = None,
) -> SalesOrder:
    """Create a standalone Sales Order (no GL impact; operational document)."""
    so = SalesOrder(
        number=next_number(session, "SO", order_date),
        order_date=order_date,
        customer_id=customer_id,
        quotation_id=quotation_id,
        notes=notes,
        status=DocStatus.DRAFT,
    )
    for l in lines:
        so.lines.append(SalesOrderLine(
            product_id=l.product_id, description=l.description,
            qty=l.qty, unit_price=l.unit_price, tax_rate=l.tax_rate,
        ))
    session.add(so)
    session.flush()
    return so


def convert_quotation_to_order(session: Session, quotation_id: int,
                                order_date: date) -> SalesOrder:
    quo = session.get(Quotation, quotation_id)
    if not quo:
        raise ValueError(f"Quotation {quotation_id} not found.")
    so = SalesOrder(
        number=next_number(session, "SO", order_date),
        order_date=order_date,
        customer_id=quo.customer_id,
        quotation_id=quo.id,
        notes=quo.notes,
        status=DocStatus.DRAFT,
    )
    for l in quo.lines:
        so.lines.append(SalesOrderLine(
            product_id=l.product_id, description=l.description,
            qty=l.qty, unit_price=l.unit_price, tax_rate=l.tax_rate,
        ))
    session.add(so)
    quo.status = DocStatus.POSTED
    session.flush()
    return so


# ---- invoice (posts to GL) -----------------------------------------------


def issue_invoice(
    session: Session, *, customer_id: int, invoice_date: date,
    lines: Iterable[LineInput],
    due_date: Optional[date] = None,
    sales_order_id: Optional[int] = None,
    notes: Optional[str] = None,
    currency_code: str = "NGN",
    fx_rate: Optional[float] = None,
) -> SalesInvoice:
    """Issue a sales invoice and post BOTH the revenue JE and the COGS JE.

    Multi-currency: the invoice may be denominated in `currency_code`. Line
    amounts are in that currency; the GL is posted in NGN at `fx_rate` (NGN
    per 1 unit, captured at issue — looked up if not supplied). COGS/inventory
    stay in NGN because product cost is held in NGN.

    Revenue JE (per invoice, in NGN):
        DR Accounts Receivable     gross × fx
            CR Sales                subtotal × fx
            CR Output VAT           tax_total × fx

    COGS JE (per invoice — sums all stockable lines, already NGN):
        DR COGS                    sum(qty × avg_cost)
            CR Inventory           sum(qty × avg_cost)
    Plus a StockMovement per stockable line decrementing on-hand.
    """
    from . import fx as fx_svc

    accts = _resolve_accounts(session)
    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")

    authz.require_perm("post.invoice")
    lines = list(lines)
    if not lines:
        raise ValueError("An invoice needs at least one line.")

    currency_code = (currency_code or "NGN").upper()
    rate = fx_svc.resolve_rate(session, currency_code, fx_rate=fx_rate,
                                as_of=invoice_date)

    def _ngn(amount: float) -> float:
        return round(amount * rate, 2)

    invoice = SalesInvoice(
        number=next_number(session, "INV", invoice_date),
        invoice_date=invoice_date,
        due_date=due_date,
        customer_id=customer_id,
        sales_order_id=sales_order_id,
        notes=notes,
        status=DocStatus.DRAFT,
        currency_code=currency_code,
        fx_rate=rate,
    )
    for l in lines:
        unit_cost = 0.0
        if l.product_id:
            prod = session.get(Product, l.product_id)
            if prod and prod.is_stockable:
                unit_cost = prod.avg_cost
        invoice.lines.append(SalesInvoiceLine(
            product_id=l.product_id, description=l.description,
            qty=l.qty, unit_price=l.unit_price,
            unit_cost=unit_cost, tax_rate=l.tax_rate,
        ))
    session.add(invoice)
    session.flush()

    # Revenue JE — amounts converted to NGN at the captured rate.
    ar_account_id = (customer.receivable_account_id or accts["AR"].id)
    rev_lines: list[JELine] = [JELine(
        account_id=ar_account_id, debit=_ngn(invoice.grand_total),
        memo=f"AR — {customer.name}", customer_id=customer.id,
    )]
    # Group revenue lines by product income_account if set, else default.
    rev_by_acct: dict[int, float] = {}
    for line in invoice.lines:
        income_acct = accts["REV"].id
        if line.product_id:
            prod = session.get(Product, line.product_id)
            if prod and prod.income_account_id:
                income_acct = prod.income_account_id
        rev_by_acct[income_acct] = rev_by_acct.get(income_acct, 0.0) + line.subtotal
    for acct_id, amt in rev_by_acct.items():
        if amt:
            rev_lines.append(JELine(account_id=acct_id, credit=_ngn(amt),
                                    memo=f"Revenue — invoice {invoice.number}"))
    if invoice.tax_total:
        # Sign-aware: a negative tax total (e.g. a tax credit line) is a debit
        # reversal of output VAT, not a negative credit (which post_journal
        # rejects). Keeps every debit/credit non-negative.
        tax_ngn = _ngn(invoice.tax_total)
        tax_line = (JELine(account_id=accts["VAT_OUT"].id, credit=tax_ngn,
                           memo=f"Output VAT — invoice {invoice.number}")
                    if tax_ngn >= 0 else
                    JELine(account_id=accts["VAT_OUT"].id, debit=-tax_ngn,
                           memo=f"Output VAT (reversal) — invoice {invoice.number}"))
        rev_lines.append(tax_line)
    rev_je = post_journal(
        session, invoice_date,
        f"Sales invoice {invoice.number} to {customer.name}",
        rev_lines, source_kind="INVOICE", source_id=invoice.id,
    )
    invoice.je_id = rev_je.id

    # COGS JE + stock movements.
    cogs_total = 0.0
    cogs_lines_by_acct: dict[int, float] = {}
    inv_lines_by_acct: dict[int, float] = {}
    for line in invoice.lines:
        if not line.product_id:
            continue
        prod = session.get(Product, line.product_id)
        if not prod or not prod.is_stockable:
            continue
        unit_cost = line.unit_cost
        line_cost = round(line.qty * unit_cost, 2)
        if line_cost <= 0:
            # Still record stock-out even if cost is zero.
            inv_svc.record_stock_out(
                session, prod, qty=line.qty, on=invoice_date,
                unit_cost=unit_cost, source_kind="INVOICE", source_id=invoice.id,
                memo=f"Sale — invoice {invoice.number}",
            )
            continue
        cogs_acct = prod.cogs_account_id or accts["COGS"].id
        inv_acct = prod.inventory_account_id or accts["INV"].id
        cogs_lines_by_acct[cogs_acct] = cogs_lines_by_acct.get(cogs_acct, 0.0) + line_cost
        inv_lines_by_acct[inv_acct] = inv_lines_by_acct.get(inv_acct, 0.0) + line_cost
        cogs_total += line_cost
        inv_svc.record_stock_out(
            session, prod, qty=line.qty, on=invoice_date,
            unit_cost=unit_cost, source_kind="INVOICE", source_id=invoice.id,
            memo=f"Sale — invoice {invoice.number}",
        )

    if cogs_total > 0:
        cogs_je_lines: list[JELine] = []
        for acct_id, amt in cogs_lines_by_acct.items():
            cogs_je_lines.append(JELine(account_id=acct_id, debit=amt,
                                        memo=f"COGS — invoice {invoice.number}"))
        for acct_id, amt in inv_lines_by_acct.items():
            cogs_je_lines.append(JELine(account_id=acct_id, credit=amt,
                                        memo=f"Stock issued — invoice {invoice.number}"))
        cogs_je = post_journal(
            session, invoice_date,
            f"COGS for invoice {invoice.number}",
            cogs_je_lines, source_kind="INVOICE_COGS", source_id=invoice.id,
        )
        invoice.cogs_je_id = cogs_je.id

    invoice.status = DocStatus.POSTED
    session.flush()
    return invoice


# ---- receipt --------------------------------------------------------------


def record_receipt(
    session: Session, *, customer_id: int, receipt_date: date,
    amount: float, bank_account_id: int,
    invoice_id: Optional[int] = None,
    method: str = "BANK", reference: Optional[str] = None,
    settlement_fx_rate: Optional[float] = None,
) -> Receipt:
    """Record cash in from a customer. Posts DR Bank / CR AR (+ realized FX).

    For an NGN invoice `amount` is NGN and there is no FX. For a foreign
    invoice, `amount` is in the INVOICE's currency (the portion being
    settled); `settlement_fx_rate` (NGN per unit at settlement; defaults to
    the invoice's issue rate) determines the NGN that hits the bank. The
    difference between NGN received and the AR cleared at the issue rate is
    booked to Foreign Exchange Gain/Loss.
    """
    from . import fx as fx_svc

    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")
    bank = session.get(BankAccount, bank_account_id)
    if not bank:
        raise ValueError(f"Bank account {bank_account_id} not found.")

    authz.require_perm("post.receipt")
    # Idempotency: a repeated (customer, reference) is a retry/replay, not a new
    # receipt. Return the existing one rather than double-posting the cash JE.
    if reference:
        dup = session.execute(
            select(Receipt).where(Receipt.customer_id == customer_id,
                                  Receipt.reference == reference)
        ).scalars().first()
        if dup is not None:
            return dup

    accts = _resolve_accounts(session)
    ar_account_id = customer.receivable_account_id or accts["AR"].id

    invoice = session.get(SalesInvoice, invoice_id) if invoice_id else None
    if invoice and amount > invoice.outstanding + 0.01:
        raise ValueError(
            f"Receipt {amount:,.2f} exceeds the outstanding balance "
            f"{invoice.outstanding:,.2f} on {invoice.number}. Record the excess "
            "as a separate unapplied receipt (customer advance) instead.")
    issue_rate = invoice.fx_rate if invoice else 1.0
    settle_rate = settlement_fx_rate if settlement_fx_rate is not None else issue_rate

    ngn_to_bank = round(amount * settle_rate, 2)      # cash actually received
    ar_cleared = round(amount * issue_rate, 2)        # AR booked at issue rate
    fx_diff = round(ngn_to_bank - ar_cleared, 2)      # +gain / -loss

    receipt = Receipt(
        number=next_number(session, "RCT", receipt_date),
        receipt_date=receipt_date,
        customer_id=customer_id,
        invoice_id=invoice_id,
        bank_account_id=bank_account_id,
        amount=ngn_to_bank,
        # Amount applied to the invoice, in the INVOICE's currency — so a void
        # subtracts exactly what was added to invoice.amount_paid (which is
        # tracked in invoice currency), not the NGN cash figure.
        applied_amount=amount,
        method=method,
        reference=reference,
        status=DocStatus.DRAFT,
    )
    session.add(receipt)
    session.flush()

    je_lines = [
        JELine(account_id=bank.gl_account_id, debit=ngn_to_bank,
               memo=f"Receipt from {customer.name}"),
        JELine(account_id=ar_account_id, credit=ar_cleared,
               memo=f"AR settled — {customer.name}", customer_id=customer.id),
    ]
    if abs(fx_diff) >= 0.01:
        fx_acct = fx_svc.fx_gainloss_account_id(session)
        if fx_diff > 0:  # received more NGN than booked → gain (credit income)
            je_lines.append(JELine(account_id=fx_acct, credit=fx_diff,
                                    memo="Realized FX gain"))
        else:            # received less → loss (debit income account)
            je_lines.append(JELine(account_id=fx_acct, debit=-fx_diff,
                                    memo="Realized FX loss"))

    je = post_journal(
        session, receipt_date,
        f"Receipt {receipt.number} from {customer.name}",
        je_lines, source_kind="RECEIPT", source_id=receipt.id,
    )
    receipt.je_id = je.id
    receipt.status = DocStatus.POSTED

    # Invoice amount_paid is tracked in the invoice's own currency.
    if invoice:
        invoice.amount_paid = round(invoice.amount_paid + amount, 2)
        if invoice.amount_paid + 0.01 >= invoice.grand_total:
            invoice.status = DocStatus.PAID
        elif invoice.amount_paid > 0:
            invoice.status = DocStatus.PARTIAL
    session.flush()
    return receipt
