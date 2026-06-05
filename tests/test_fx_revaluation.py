"""Unrealized FX revaluation marks open foreign AR/AP to the period-end rate."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select


def _seed(s):
    from bizclinik_erp.models import Customer, Product
    s.add(Customer(code="C1", name="US Client"))
    s.add(Product(sku="P1", name="Widget", standard_price=100,
                  standard_cost=40, is_stockable=False))
    s.flush()


def test_open_usd_receivable_revalued(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, fx
    from bizclinik_erp.models import Customer, Product

    with get_session() as s:
        _seed(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1500.0)   # issue rate

    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
            currency_code="USD",
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                   qty=10, unit_price=100, tax_rate=0.0)],
        )  # USD 1000 outstanding, booked at 1500

    # Period-end: NGN weakens to 1600.
    with get_session() as s:
        fx.set_rate(s, "USD", date(2026, 1, 31), 1600.0)

    with get_session() as s:
        rep = fx.unrealized_fx_revaluation(s, as_of=date(2026, 1, 31))
        assert len(rep["receivables"]) == 1
        r = rep["receivables"][0]
        assert r["outstanding_fc"] == 1000.0
        assert r["booked_rate"] == 1500.0
        assert r["current_rate"] == 1600.0
        # 1000 * (1600 - 1500) = +100,000 NGN unrealized gain on the asset.
        assert r["unrealized"] == 100000.0
        assert rep["net_unrealized"] == 100000.0


def test_ngn_invoice_not_revalued(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, fx
    from bizclinik_erp.models import Customer, Product

    with get_session() as s:
        _seed(s)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                   qty=5, unit_price=100, tax_rate=0.0)],
        )  # NGN invoice
    with get_session() as s:
        rep = fx.unrealized_fx_revaluation(s, as_of=date(2026, 1, 31))
        assert rep["receivables"] == []
        assert rep["net_unrealized"] == 0.0


def test_missing_rate_is_skipped_not_fatal(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales, fx
    from bizclinik_erp.models import Customer, Product

    with get_session() as s:
        _seed(s)
        fx.set_rate(s, "USD", date(2026, 1, 1), 1500.0)
    with get_session() as s:
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        sales.issue_invoice(
            s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
            currency_code="USD",
            lines=[sales.LineInput(product_id=prod.id, description="Widget",
                                   qty=1, unit_price=100, tax_rate=0.0)],
        )
    # Revalue as of a date BEFORE any rate exists -> skipped, no crash.
    with get_session() as s:
        rep = fx.unrealized_fx_revaluation(s, as_of=date(2025, 12, 1))
        assert rep["receivables"] == []
        assert len(rep["skipped"]) == 1
        assert rep["net_unrealized"] == 0.0
