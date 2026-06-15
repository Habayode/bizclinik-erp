"""A negative tax line (e.g. a tax credit) must post as a reversal on the
correct side rather than a negative debit/credit that post_journal rejects;
and an empty document is refused up-front with a clear message."""
from __future__ import annotations

from datetime import date

import pytest


def _customer(s, code="C1", name="Acme Ltd"):
    from bizclinik_erp.models import Customer
    c = Customer(code=code, name=name); s.add(c); s.flush(); return c


def _supplier(s, code="S1", name="Beta Ltd"):
    from bizclinik_erp.models import Supplier
    sp = Supplier(code=code, name=name); s.add(sp); s.flush(); return sp


def test_empty_invoice_is_rejected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sv
    with get_session() as s:
        cid = _customer(s).id
        with pytest.raises(ValueError, match="at least one line"):
            sv.issue_invoice(s, customer_id=cid, invoice_date=date(2026, 1, 1),
                             lines=[])


def test_empty_bill_is_rejected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import purchase as pu
    with get_session() as s:
        sid = _supplier(s).id
        with pytest.raises(ValueError, match="at least one line"):
            pu.receive_bill(s, supplier_id=sid, bill_date=date(2026, 1, 1),
                            lines=[])


def test_negative_tax_invoice_posts_balanced(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sv
    from bizclinik_erp.models import DocStatus, JournalEntry
    with get_session() as s:
        cid = _customer(s).id
        inv = sv.issue_invoice(
            s, customer_id=cid, invoice_date=date(2026, 1, 1),
            lines=[sv.LineInput(product_id=None, description="svc", qty=1.0,
                                unit_price=100_000.0, tax_rate=-0.05)])
        # Previously raised "must be non-negative"; now it posts.
        assert inv.status == DocStatus.POSTED and inv.je_id is not None
        je = s.get(JournalEntry, inv.je_id)
        assert round(je.total_debit, 2) == round(je.total_credit, 2)


def test_negative_tax_bill_posts_balanced(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import purchase as pu
    from bizclinik_erp.models import DocStatus, JournalEntry
    with get_session() as s:
        sid = _supplier(s).id
        bill = pu.receive_bill(
            s, supplier_id=sid, bill_date=date(2026, 1, 1),
            lines=[pu.POLineInput(product_id=None, description="svc", qty=1.0,
                                  unit_cost=100_000.0, tax_rate=-0.05)])
        assert bill.status == DocStatus.POSTED and bill.je_id is not None
        je = s.get(JournalEntry, bill.je_id)
        assert round(je.total_debit, 2) == round(je.total_credit, 2)
