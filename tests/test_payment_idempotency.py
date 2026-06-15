"""Receipt/payment idempotency: a repeated reference is a retry/replay, not a
second cash movement. The service returns the existing doc; the DB unique
index (customer/supplier + reference) is the concurrency backstop; reference-
less docs stay distinct (NULL semantics) so genuine repeats still post."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _bank_id(s, code="BANK1"):
    from bizclinik_erp.models import BankAccount
    return s.execute(select(BankAccount).where(BankAccount.code == code)).scalar_one().id


def _add_customer(s, code="CUST-1", name="Acme Trading Ltd"):
    from bizclinik_erp.models import Customer
    c = Customer(code=code, name=name); s.add(c); s.flush(); return c


def _add_supplier(s, code="SUP-1", name="Beta Supplies Ltd"):
    from bizclinik_erp.models import Supplier
    sp = Supplier(code=code, name=name); s.add(sp); s.flush(); return sp


# --------------------------------------------------------------------------- #
# Service-level guard                                                         #
# --------------------------------------------------------------------------- #

def test_receipt_same_reference_is_idempotent(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sv
    from bizclinik_erp.models import Receipt, JournalEntry
    with get_session() as s:
        cid = _add_customer(s).id
        bid = _bank_id(s)
        inv = sv.issue_invoice(
            s, customer_id=cid, invoice_date=date(2026, 1, 1),
            lines=[sv.LineInput(product_id=None, description="svc", qty=1.0,
                                unit_price=100_000, tax_rate=0.0)])
        inv_id = inv.id
    with get_session() as s:
        r1 = sv.record_receipt(s, customer_id=cid, receipt_date=date(2026, 1, 5),
                               amount=50_000, bank_account_id=bid,
                               invoice_id=inv_id, reference="TRX-99")
        id1 = r1.id
    with get_session() as s:   # the retry
        r2 = sv.record_receipt(s, customer_id=cid, receipt_date=date(2026, 1, 5),
                               amount=50_000, bank_account_id=bid,
                               invoice_id=inv_id, reference="TRX-99")
        assert r2.id == id1
    with get_session() as s:
        assert s.query(Receipt).count() == 1
        assert s.query(JournalEntry).filter_by(source_kind="RECEIPT").count() == 1
        inv = s.get(type(inv), inv_id)
        assert inv.amount_paid == 50_000     # not double-counted


def test_distinct_references_both_post(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sv
    from bizclinik_erp.models import Receipt
    with get_session() as s:
        cid = _add_customer(s).id; bid = _bank_id(s)
        inv = sv.issue_invoice(
            s, customer_id=cid, invoice_date=date(2026, 1, 1),
            lines=[sv.LineInput(product_id=None, description="svc", qty=1.0,
                                unit_price=100_000, tax_rate=0.0)])
        inv_id = inv.id
    with get_session() as s:
        sv.record_receipt(s, customer_id=cid, receipt_date=date(2026, 1, 5),
                          amount=50_000, bank_account_id=bid, invoice_id=inv_id,
                          reference="A")
        sv.record_receipt(s, customer_id=cid, receipt_date=date(2026, 1, 6),
                          amount=50_000, bank_account_id=bid, invoice_id=inv_id,
                          reference="B")
    with get_session() as s:
        assert s.query(Receipt).count() == 2


def test_payment_same_reference_is_idempotent(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import purchase as pu
    from bizclinik_erp.models import Payment, JournalEntry
    with get_session() as s:
        sid = _add_supplier(s).id; bid = _bank_id(s)
    with get_session() as s:
        p1 = pu.record_payment(s, supplier_id=sid, payment_date=date(2026, 1, 5),
                               amount=70_000, bank_account_id=bid, reference="PX-1")
        id1 = p1.id
    with get_session() as s:
        p2 = pu.record_payment(s, supplier_id=sid, payment_date=date(2026, 1, 5),
                               amount=70_000, bank_account_id=bid, reference="PX-1")
        assert p2.id == id1
    with get_session() as s:
        assert s.query(Payment).count() == 1
        assert s.query(JournalEntry).filter_by(source_kind="PAYMENT").count() == 1


# --------------------------------------------------------------------------- #
# DB index backstop + NULL semantics                                          #
# --------------------------------------------------------------------------- #

def test_unique_index_blocks_duplicate_reference(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Receipt
    with get_session() as s:
        cid = _add_customer(s).id; bid = _bank_id(s)
        s.add(Receipt(number="RCT-X-1", receipt_date=date(2026, 1, 1),
                      customer_id=cid, bank_account_id=bid, amount=1.0,
                      reference="DUP"))
        s.flush()
        s.add(Receipt(number="RCT-X-2", receipt_date=date(2026, 1, 1),
                      customer_id=cid, bank_account_id=bid, amount=1.0,
                      reference="DUP"))
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()   # clear the failed flush so get_session can exit cleanly


def test_referenceless_receipts_stay_distinct(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Receipt
    with get_session() as s:
        cid = _add_customer(s).id; bid = _bank_id(s)
        for n in ("RCT-Y-1", "RCT-Y-2", "RCT-Y-3"):
            s.add(Receipt(number=n, receipt_date=date(2026, 1, 1),
                          customer_id=cid, bank_account_id=bid, amount=1.0,
                          reference=None))
        s.flush()   # NULL references must not collide
    with get_session() as s:
        assert s.query(Receipt).count() == 3
