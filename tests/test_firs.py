"""Tests for FIRS e-invoice generation: payload, IRN, QR, and persistence."""
from __future__ import annotations

from datetime import date


def _seed_company_customer_product(s):
    from bizclinik_erp.models import Company, Customer, Product
    s.add(Company(name="BizClinik Demo Ltd", rc_number="RC123456",
                  vat_number="VAT-99887766", address="12 Marina, Lagos"))
    s.add(Customer(code="C1", name="Acme Stores",
                   address="4 Allen Avenue, Ikeja"))
    s.add(Product(sku="P1", name="Widget", standard_price=1000,
                  standard_cost=600, is_stockable=True))
    s.flush()


def _issue_invoice(s):
    from bizclinik_erp.services import sales
    from bizclinik_erp.models import Customer, Product
    from sqlalchemy import select
    cust = s.execute(select(Customer)).scalar_one()
    prod = s.execute(select(Product)).scalar_one()
    return sales.issue_invoice(
        s, customer_id=cust.id, invoice_date=date(2026, 6, 1),
        lines=[sales.LineInput(product_id=prod.id, description="Widget",
                               qty=2, unit_price=1000, tax_rate=0.075)],
    )


def test_einvoice_dict_totals_and_irn(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.firs_einvoice import build_einvoice_dict

    with get_session() as s:
        _seed_company_customer_product(s)

    with get_session() as s:
        inv = _issue_invoice(s)
        inv_id = inv.id
        grand_total = inv.grand_total
        subtotal = inv.subtotal
        tax_total = inv.tax_total

    with get_session() as s:
        d = build_einvoice_dict(s, inv_id)

        # Legal monetary total matches the invoice grand total.
        assert d["legal_monetary_total"]["payable_amount"] == grand_total
        assert d["legal_monetary_total"]["tax_inclusive_amount"] == grand_total
        assert d["legal_monetary_total"]["tax_exclusive_amount"] == subtotal
        assert d["tax_summary"]["taxable_base"] == subtotal
        assert d["tax_summary"]["total_vat"] == tax_total

        # IRN format: {invoice_number}-{rc_or_tin}-{yyyymmdd}.
        # Supplier TIN prefers vat_number ("VAT-99887766").
        expected_irn = f"{d['invoice_number']}-VAT-99887766-20260601"
        assert d["irn"] == expected_irn
        assert d["currency"] == "NGN"
        assert d["csid"]  # placeholder present
        assert len(d["line_items"]) == 1


def test_qr_payload_non_empty_contains_irn(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.firs_einvoice import (
        build_einvoice_dict, einvoice_qr_payload,
    )

    with get_session() as s:
        _seed_company_customer_product(s)

    with get_session() as s:
        inv = _issue_invoice(s)
        inv_id = inv.id

    with get_session() as s:
        d = build_einvoice_dict(s, inv_id)
        qr = einvoice_qr_payload(d)
        assert qr
        assert d["irn"] in qr
        # Compact pipe-delimited form: IRN|date|tin|total|vat
        assert qr.count("|") == 4


def test_generate_for_invoice_persists_submission(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import firs
    from bizclinik_erp.models import EInvoiceStatus, EInvoiceSubmission

    with get_session() as s:
        _seed_company_customer_product(s)

    with get_session() as s:
        inv = _issue_invoice(s)
        inv_id = inv.id

    with get_session() as s:
        sub = firs.generate_for_invoice(s, inv_id)
        assert sub.id is not None
        assert sub.status == EInvoiceStatus.GENERATED
        assert sub.invoice_id == inv_id
        assert sub.irn
        assert sub.qr_payload and sub.irn in sub.qr_payload

    # Row persisted and listable.
    with get_session() as s:
        subs = firs.list_submissions(s)
        assert len(subs) == 1
        assert subs[0].status == EInvoiceStatus.GENERATED
        row = s.get(EInvoiceSubmission, subs[0].id)
        assert row is not None
