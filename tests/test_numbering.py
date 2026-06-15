"""Atomic document numbering: sequential, per-(kind, year), and seeded from any
pre-existing documents so a freshly-added counter never reissues a number that
legacy data already used."""
from __future__ import annotations

from datetime import date


def test_sequential_and_isolated_by_kind_and_year(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.numbering import next_number
    with get_session() as s:
        assert next_number(s, "INV", date(2026, 1, 1)) == "INV-2026-0001"
        assert next_number(s, "INV", date(2026, 1, 1)) == "INV-2026-0002"
        assert next_number(s, "INV", date(2027, 1, 1)) == "INV-2027-0001"  # year resets
        assert next_number(s, "PAY", date(2026, 1, 1)) == "PAY-2026-0001"  # kind isolated


def test_counter_seeds_from_existing_documents(fresh_db):
    """Simulates a legacy DB: documents already exist but the counter row does
    not. The next number must continue from the existing max, not restart."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sv
    from bizclinik_erp.services.numbering import next_number
    from bizclinik_erp.models import Customer, DocCounter

    with get_session() as s:
        c = Customer(code="C1", name="X Ltd"); s.add(c); s.flush()
        cid = c.id
        for _ in range(3):   # -> INV-2026-0001..0003
            sv.issue_invoice(
                s, customer_id=cid, invoice_date=date(2026, 1, 1),
                lines=[sv.LineInput(product_id=None, description="x", qty=1.0,
                                    unit_price=100.0, tax_rate=0.0)])
    with get_session() as s:   # drop the counter, leaving the invoices behind
        s.query(DocCounter).filter_by(key="INV-2026").delete()
    with get_session() as s:
        assert next_number(s, "INV", date(2026, 1, 1)) == "INV-2026-0004"


def test_allocations_within_a_session_are_distinct(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.numbering import next_number
    with get_session() as s:
        nums = [next_number(s, "JE", date(2026, 1, 1)) for _ in range(25)]
    assert len(set(nums)) == 25
    assert nums[0] == "JE-2026-0001" and nums[-1] == "JE-2026-0025"
