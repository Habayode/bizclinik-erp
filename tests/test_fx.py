"""Multi-currency tests: foreign invoices/bills post NGN, realized FX on settle."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, func


def _seed_cust_sup_prod(s):
    from bizclinik_erp.models import Customer, Supplier, Product
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


def test_currencies_seeded(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Currency
    with get_session() as s:
        ngn = s.get(Currency, "NGN")
        assert ngn is not None and ngn.is_base
        assert s.get(Currency, "USD") is not None


def test_get_rate_base_is_one(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import fx
    with get_session() as s:
        assert fx.get_rate(s, "NGN") == 1.0


def test_foreign_invoice_posts_ngn(fresh_db):
    """USD invoice at rate 1600 → GL in NGN, TB balanced."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, fx
    from bizclinik_erp.models import Customer, Product, SalesInvoice
    with get_session() as s:
        _seed_cust_sup_prod(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1600.0)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        inv = sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
            currency_code="USD",
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                     qty=10, unit_price=100, tax_rate=0.0)],
        )
        # document is USD 1000
        assert inv.currency_code == "USD"
        assert inv.fx_rate == 1600.0
        assert round(inv.grand_total, 2) == 1000.0
        inv_id = inv.id
    with get_session() as s:
        # AR posted in NGN = 1000 * 1600 = 1,600,000
        from bizclinik_erp.models import JournalLine, Account
        ar = s.execute(select(Account).where(Account.code == "1130")).scalar_one()
        ar_dr = s.execute(
            select(func.coalesce(func.sum(JournalLine.debit), 0))
            .where(JournalLine.account_id == ar.id)
        ).scalar_one()
        assert round(ar_dr, 2) == 1_600_000.00
        dr, cr = _tb(s)
        assert abs(dr - cr) < 0.01


def test_realized_fx_gain_on_receipt(fresh_db):
    """USD invoice at 1600, settled at 1650 → FX gain on the 50/unit move."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, fx
    from bizclinik_erp.models import Customer, Product, BankAccount, Account, JournalLine
    with get_session() as s:
        _seed_cust_sup_prod(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1600.0)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bank = s.execute(select(BankAccount).where(BankAccount.code == "BANK1")).scalar_one()
        inv = sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
            currency_code="USD",
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                     qty=10, unit_price=100, tax_rate=0.0)],
        )
        # settle full USD 1000 at rate 1650
        sales.record_receipt(s, customer_id=cust.id, receipt_date=date(2026, 2, 1),
                              amount=1000.0, bank_account_id=bank.id,
                              invoice_id=inv.id, settlement_fx_rate=1650.0)
    with get_session() as s:
        # FX gain account 4300 should have a credit of 1000*(1650-1600)=50,000
        fxa = s.execute(select(Account).where(Account.code == "4300")).scalar_one()
        fx_cr = s.execute(
            select(func.coalesce(func.sum(JournalLine.credit), 0))
            .where(JournalLine.account_id == fxa.id)
        ).scalar_one()
        assert round(fx_cr, 2) == 50_000.00
        # AR fully cleared
        ar = s.execute(select(Account).where(Account.code == "1130")).scalar_one()
        ar_dr = s.execute(select(func.coalesce(func.sum(JournalLine.debit), 0)).where(JournalLine.account_id == ar.id)).scalar_one()
        ar_cr = s.execute(select(func.coalesce(func.sum(JournalLine.credit), 0)).where(JournalLine.account_id == ar.id)).scalar_one()
        assert abs(ar_dr - ar_cr) < 0.01  # AR net zero
        dr, cr = _tb(s)
        assert abs(dr - cr) < 0.01


def test_ngn_invoice_unaffected(fresh_db):
    """Plain NGN invoice behaves exactly as before (rate 1.0, no FX)."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales
    from bizclinik_erp.models import Customer, Product, BankAccount, Account, JournalLine
    with get_session() as s:
        _seed_cust_sup_prod(s)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bank = s.execute(select(BankAccount).where(BankAccount.code == "BANK1")).scalar_one()
        inv = sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 3, 1),
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                     qty=5, unit_price=1000, tax_rate=0.075)],
        )
        assert inv.currency_code == "NGN" and inv.fx_rate == 1.0
        sales.record_receipt(s, customer_id=cust.id, receipt_date=date(2026, 3, 5),
                              amount=inv.grand_total, bank_account_id=bank.id,
                              invoice_id=inv.id)
    with get_session() as s:
        # No FX gain/loss posted
        fxa = s.execute(select(Account).where(Account.code == "4300")).scalar_one()
        n = s.execute(select(func.count(JournalLine.id)).where(JournalLine.account_id == fxa.id)).scalar_one()
        assert n == 0
        dr, cr = _tb(s)
        assert abs(dr - cr) < 0.01


def test_foreign_bill_posts_ngn_and_stock_valued_ngn(fresh_db):
    """USD bill at 1600 → inventory valued in NGN, TB balanced."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import purchase, fx
    from bizclinik_erp.models import Supplier, Product
    with get_session() as s:
        _seed_cust_sup_prod(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1600.0)
    with get_session() as s:
        sup = s.execute(select(Supplier)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        purchase.receive_bill(
            s, supplier_id=sup.id, bill_date=date(2026, 1, 12),
            currency_code="USD",
            lines=[purchase.POLineInput(product_id=prod.id, description="Widget",
                                          qty=100, unit_cost=5, tax_rate=0.0)],
        )
    with get_session() as s:
        prod = s.execute(select(Product)).scalar_one()
        # avg cost should be NGN: 5 USD * 1600 = 8000 NGN
        assert round(prod.avg_cost, 2) == 8000.00
        dr, cr = _tb(s)
        assert abs(dr - cr) < 0.01
