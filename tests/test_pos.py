"""Retail POS: a checkout rings up a full, balanced sale (revenue + VAT + COGS +
stock-out) and settles payment; the walk-in customer is shared; the retail
navigation is POS-first."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select


def _cash_account_id(s):
    from bizclinik_erp.models import Account
    return s.execute(select(Account).where(Account.code == "1000")).scalar_one().id


def _seed_store(s):
    """A till bank account + a stocked product (avg cost 600, 10 on hand)."""
    from bizclinik_erp.models import BankAccount, Product
    from bizclinik_erp.services import inventory as inv
    bank = BankAccount(code="TILL", name="Cash Till", gl_account_id=_cash_account_id(s))
    s.add(bank)
    p = Product(sku="MILK1L", name="Milk 1L", standard_price=1000.0, is_stockable=True)
    s.add(p)
    s.flush()
    inv.record_stock_in(s, p, qty=10, unit_cost=600.0, on=date.today())
    return bank.id, p.id


def test_walkin_customer_is_shared(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import pos
    with get_session() as s:
        a = pos.walkin_customer(s).id
    with get_session() as s:
        b = pos.walkin_customer(s).id
    assert a == b  # get-or-create, not duplicated


def test_checkout_posts_balanced_sale_and_reduces_stock(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Product, Receipt
    from bizclinik_erp.services import pos
    from bizclinik_erp.services.ledger import trial_balance

    with get_session() as s:
        bank_id, pid = _seed_store(s)

    with get_session() as s:
        res = pos.checkout(s, lines=[pos.CartLine(product_id=pid, qty=2.0)],
                           bank_account_id=bank_id, method="CASH", tendered=2500.0)

    # 2 × ₦1,000 = 2,000 + 7.5% VAT = ₦2,150 total; change from ₦2,500 = ₦350.
    assert res["total"] == 2150.0
    assert res["tax"] == 150.0
    assert res["change"] == 350.0
    assert res["items"] == 1

    with get_session() as s:
        p = s.get(Product, pid)
        assert p.qty_on_hand == 8.0                       # 10 - 2 sold
        assert s.execute(select(Receipt)).scalars().first() is not None
        rows = trial_balance(s)
        dr = round(sum(r["debit"] for r in rows), 2)
        cr = round(sum(r["credit"] for r in rows), 2)
        assert abs(dr - cr) < 0.01                        # books still balance


def test_checkout_empty_cart_raises(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import pos
    import pytest
    with get_session() as s:
        bank_id, _ = _seed_store(s)
    with get_session() as s:
        with pytest.raises(ValueError):
            pos.checkout(s, lines=[], bank_account_id=bank_id)


def test_retail_nav_is_pos_first():
    from bizclinik_erp.nav import build_nav_spec
    spec = build_nav_spec("retail")
    groups = {g for g, _ in spec}
    assert "Till" in groups
    till_pages = dict(spec)["Till"]
    assert till_pages[0]["title"] == "Point of Sale"
    assert till_pages[0]["default"] is True


def test_checkout_applies_line_discount_and_returns_lines(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import pos
    with get_session() as s:
        bank_id, pid = _seed_store(s)
    with get_session() as s:
        res = pos.checkout(
            s, lines=[pos.CartLine(product_id=pid, qty=2.0, discount_pct=0.10)],
            bank_account_id=bank_id, method="CARD")
    # 2 × ₦1,000 less 10% = ₦1,800 + 7.5% VAT = ₦1,935.
    assert res["subtotal"] == 1800.0
    assert res["total"] == 1935.0
    assert res["lines"][0]["price"] == 900.0          # discounted unit price
    assert res["lines"][0]["line_total"] == 1935.0


def test_receipt_totals_foot_and_match_the_ledger(fresh_db):
    """On sub-cent prices the receipt subtotal+VAT must equal the total and the
    posted invoice (regression: the receipt used to recompute VAT independently
    and could be a cent off)."""
    from datetime import date
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import BankAccount, Product, SalesInvoice
    from bizclinik_erp.services import inventory as invsvc, pos
    with get_session() as s:
        bank = BankAccount(code="TILL2", name="Till", gl_account_id=_cash_account_id(s))
        s.add(bank)
        p = Product(sku="ODD", name="Odd priced 10.10", standard_price=10.10,
                    is_stockable=True)
        s.add(p)
        s.flush()
        invsvc.record_stock_in(s, p, qty=10, unit_cost=5.0, on=date.today())
        bid, pid = bank.id, p.id
    with get_session() as s:
        res = pos.checkout(s, lines=[pos.CartLine(product_id=pid, qty=2.0)],
                           bank_account_id=bid, method="CARD")
        inv = s.get(SalesInvoice, res["invoice_id"])
        assert round(res["subtotal"] + res["tax"], 2) == res["total"]   # foots
        assert res["total"] == round(inv.grand_total, 2)                # == GL
        assert res["tax"] == round(inv.tax_total, 2)                    # VAT == GL
        assert round(sum(l["line_total"] for l in res["lines"]), 2) == res["total"]


def test_find_product_by_barcode_then_sku(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Product
    from bizclinik_erp.services import pos
    with get_session() as s:
        s.add(Product(sku="RICE5KG", barcode="6001234567890", name="Rice 5kg",
                      standard_price=8000.0, is_stockable=True))
    with get_session() as s:
        assert pos.find_product(s, "6001234567890").sku == "RICE5KG"  # by barcode
        assert pos.find_product(s, "RICE5KG").sku == "RICE5KG"        # by SKU
        assert pos.find_product(s, "does-not-exist") is None
