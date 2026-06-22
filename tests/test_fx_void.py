"""Voiding a receipt/payment must restore amount_paid by the amount that was
APPLIED to the document (in the document's own currency), not the NGN cash
figure. Regression for the FX void unit-mismatch: a foreign-currency receipt
used to subtract its NGN value from an invoice-currency amount_paid, corrupting
the balance and status. NGN documents are unaffected (applied == cash)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select


def _seed(s):
    from bizclinik_erp.models import Customer, Product, Supplier
    s.add(Customer(code="C1", name="US Client"))
    s.add(Supplier(code="S1", name="UK Vendor"))
    s.add(Product(sku="P1", name="Widget", standard_price=100,
                   standard_cost=40, is_stockable=True))
    s.flush()


def _tb(s):
    from bizclinik_erp.models import JournalLine
    dr = s.execute(select(func.coalesce(func.sum(JournalLine.debit), 0))).scalar_one()
    cr = s.execute(select(func.coalesce(func.sum(JournalLine.credit), 0))).scalar_one()
    return round(dr, 2), round(cr, 2)


def test_void_foreign_receipt_restores_amount_paid(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import fx, sales, voids
    from bizclinik_erp.models import (BankAccount, Customer, DocStatus, Product,
                                       SalesInvoice)
    with get_session() as s:
        _seed(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1600.0)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bank = s.execute(select(BankAccount).where(BankAccount.code == "BANK1")).scalar_one()
        inv = sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
            currency_code="USD",
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                     qty=10, unit_price=100, tax_rate=0.0)])
        rct = sales.record_receipt(
            s, customer_id=cust.id, receipt_date=date(2026, 2, 1),
            amount=1000.0, bank_account_id=bank.id, invoice_id=inv.id)
        # amount_paid is tracked in the invoice's currency (USD 1000), even
        # though the cash posted is NGN 1,600,000.
        assert round(inv.amount_paid, 2) == 1000.0
        assert round(rct.amount, 2) == 1_600_000.0
        assert inv.status == DocStatus.PAID
        inv_id, rct_id = inv.id, rct.id
    with get_session() as s:
        voids.void_receipt(s, rct_id, reason="customer reversed the transfer")
        inv = s.get(SalesInvoice, inv_id)
        # The bug subtracted 1,600,000 from 1,000 -> -1,599,000. Fixed: back to 0.
        assert round(inv.amount_paid, 2) == 0.0
        assert inv.status == DocStatus.POSTED
        dr, cr = _tb(s)
        assert abs(dr - cr) < 0.01


def test_void_foreign_receipt_with_fx_movement(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import fx, sales, voids
    from bizclinik_erp.models import (BankAccount, Customer, DocStatus, Product,
                                       SalesInvoice)
    with get_session() as s:
        _seed(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1600.0)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bank = s.execute(select(BankAccount).where(BankAccount.code == "BANK1")).scalar_one()
        inv = sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
            currency_code="USD",
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                     qty=10, unit_price=100, tax_rate=0.0)])
        rct = sales.record_receipt(
            s, customer_id=cust.id, receipt_date=date(2026, 2, 1),
            amount=1000.0, bank_account_id=bank.id, invoice_id=inv.id,
            settlement_fx_rate=1650.0)  # FX gain on settle
        inv_id, rct_id = inv.id, rct.id
    with get_session() as s:
        voids.void_receipt(s, rct_id, reason="reversed after FX settlement")
        inv = s.get(SalesInvoice, inv_id)
        assert round(inv.amount_paid, 2) == 0.0
        assert inv.status == DocStatus.POSTED
        dr, cr = _tb(s)
        assert abs(dr - cr) < 0.01  # reversal itself balanced


def test_void_ngn_receipt_regression(fresh_db):
    """Plain NGN receipt void still works exactly as before."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, voids
    from bizclinik_erp.models import (BankAccount, Customer, DocStatus, Product,
                                       SalesInvoice)
    with get_session() as s:
        _seed(s)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bank = s.execute(select(BankAccount).where(BankAccount.code == "BANK1")).scalar_one()
        inv = sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 3, 1),
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                     qty=5, unit_price=1000, tax_rate=0.075)])
        rct = sales.record_receipt(
            s, customer_id=cust.id, receipt_date=date(2026, 3, 5),
            amount=inv.grand_total, bank_account_id=bank.id, invoice_id=inv.id)
        assert inv.status == DocStatus.PAID
        inv_id, rct_id = inv.id, rct.id
    with get_session() as s:
        voids.void_receipt(s, rct_id, reason="duplicate receipt")
        inv = s.get(SalesInvoice, inv_id)
        assert round(inv.amount_paid, 2) == 0.0
        assert inv.status == DocStatus.POSTED


def test_void_foreign_payment_restores_amount_paid(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import fx, purchase, voids
    from bizclinik_erp.models import (BankAccount, Bill, DocStatus, Product,
                                       Supplier)
    with get_session() as s:
        _seed(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1600.0)
    with get_session() as s:
        sup = s.execute(select(Supplier)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bank = s.execute(select(BankAccount).where(BankAccount.code == "BANK1")).scalar_one()
        bill = purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=date(2026, 1, 12),
            currency_code="USD",
            lines=[purchase.POLineInput(product_id=prod.id, description="Widget",
                                          qty=100, unit_cost=5, tax_rate=0.0)])
        pay = purchase.record_payment(
            s, supplier_id=sup.id, payment_date=date(2026, 2, 1),
            amount=bill.grand_total, bank_account_id=bank.id, bill_id=bill.id)
        assert round(bill.amount_paid, 2) == round(bill.grand_total, 2)  # USD units
        bill_id, pay_id = bill.id, pay.id
    with get_session() as s:
        voids.void_payment(s, pay_id, reason="paid the wrong supplier")
        bill = s.get(Bill, bill_id)
        assert round(bill.amount_paid, 2) == 0.0
        assert bill.status == DocStatus.POSTED
