"""WHT certificate fallback (used when no WHT journal line exists) must compute
withholding per line at that line's own rate and report an effective rate —
not pool the subtotals and apply a single (max) rate to a statutory document."""
from __future__ import annotations

from datetime import date


def test_fallback_computes_wht_per_line(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.wht_certificate_pdf import _collect_wht_rows
    from bizclinik_erp.models import Supplier, Bill, BillLine, DocStatus
    with get_session() as s:
        sp = Supplier(code="S-WHT", name="Pro Services Ltd"); s.add(sp); s.flush()
        sid = sp.id
        b = Bill(number="BIL-2026-9001", bill_date=date(2026, 3, 1),
                 supplier_id=sid, status=DocStatus.POSTED)
        s.add(b); s.flush()
        # Two WHT-rate (5%) lines, no WHT journal -> fallback path.
        s.add(BillLine(bill_id=b.id, description="design", qty=1.0,
                       unit_cost=100_000.0, tax_rate=0.05))
        s.add(BillLine(bill_id=b.id, description="consulting", qty=1.0,
                       unit_cost=50_000.0, tax_rate=0.05))
        s.flush()
    with get_session() as s:
        rows = _collect_wht_rows(s, sid, period_start=date(2026, 1, 1),
                                 period_end=date(2026, 12, 31), wht_rate=0.05)
    assert len(rows) == 1
    r = rows[0]
    # per line: round(100000*0.05,2) + round(50000*0.05,2) = 5000 + 2500
    assert r["wht"] == 7_500.0
    assert r["gross"] == 150_000.0
    assert abs(r["rate"] - 0.05) < 1e-6           # effective rate, derived


def test_fallback_effective_rate_is_amount_over_gross(fresh_db):
    """The displayed rate is derived from the actual withheld amount / gross,
    so it stays self-consistent even if line amounts don't divide cleanly."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.wht_certificate_pdf import _collect_wht_rows
    from bizclinik_erp.models import Supplier, Bill, BillLine, DocStatus
    with get_session() as s:
        sp = Supplier(code="S-WHT2", name="Audit Partners"); s.add(sp); s.flush()
        sid = sp.id
        b = Bill(number="BIL-2026-9002", bill_date=date(2026, 4, 1),
                 supplier_id=sid, status=DocStatus.POSTED)
        s.add(b); s.flush()
        s.add(BillLine(bill_id=b.id, description="audit", qty=1.0,
                       unit_cost=333_333.33, tax_rate=0.05))
        s.flush()
    with get_session() as s:
        rows = _collect_wht_rows(s, sid, period_start=date(2026, 1, 1),
                                 period_end=date(2026, 12, 31), wht_rate=0.05)
    r = rows[0]
    assert r["wht"] == round(333_333.33 * 0.05, 2)
    assert r["rate"] == round(r["wht"] / r["gross"], 4)   # effective rate, 4dp
