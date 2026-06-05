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

        # IRN format: {clean(number)}-{clean(party)}-{yyyymmdd}. Every segment
        # is sanitised to alphanumeric, so VAT-99887766 -> VAT99887766.
        from bizclinik_erp.exporters.firs_einvoice import _clean_token
        expected_irn = f"{_clean_token(d['invoice_number'])}-VAT99887766-20260601"
        assert d["irn"] == expected_irn
        assert " " not in d["irn"]          # never any spaces in an IRN
        assert d["currency"] == "NGN"
        assert d["csid"]  # placeholder present
        assert len(d["line_items"]) == 1

        # Draft labelling embedded so it can't be mistaken for FIRS-cleared.
        assert d["document_status"] == "DRAFT"
        assert "FIRS" in d["firs_notice"]

        # TIN is a real tax id (VAT-based here), NEVER the RC number.
        assert d["supplier"]["tin"] == "VAT-99887766"
        assert d["supplier"]["rc_number"] == "RC123456"
        assert d["supplier"]["tin"] != d["supplier"]["rc_number"]


def test_irn_strips_spaces_and_tin_never_falls_back_to_rc(fresh_db):
    """A company with only an RC number that contains a space: the IRN must be
    space-free, and the supplier TIN must be None (RC is not a TIN)."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.firs_einvoice import build_einvoice_dict
    from bizclinik_erp.models import Company, Customer, Product

    with get_session() as s:
        s.add(Company(name="Wendysrack Luxe Ltd", rc_number="RC 8229227"))
        s.add(Customer(code="C1", name="amusa"))
        s.add(Product(sku="P1", name="Bag", standard_price=2900,
                      standard_cost=1500, is_stockable=True))
        s.flush()

    with get_session() as s:
        inv = _issue_invoice(s)
        inv_id = inv.id

    with get_session() as s:
        d = build_einvoice_dict(s, inv_id)
        assert " " not in d["irn"]               # 'RC 8229227' -> 'RC8229227'
        assert "RC8229227" in d["irn"]
        assert d["supplier"]["tin"] is None       # no genuine TIN on file
        assert d["supplier"]["rc_number"] == "RC 8229227"


def test_firs_service_id_used_as_irn_party_segment(fresh_db):
    """When a FIRS Service ID is set, it is the middle IRN segment."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.exporters.firs_einvoice import build_einvoice_dict
    from bizclinik_erp.models import Company, Customer, Product

    with get_session() as s:
        c = Company(name="Demo Ltd", rc_number="RC123456", vat_number="VAT-1")
        c.tin = "TIN-555"
        c.firs_service_id = "SVCID007"
        s.add(c)
        s.add(Customer(code="C1", name="Acme"))
        s.add(Product(sku="P1", name="Widget", standard_price=1000,
                      standard_cost=600, is_stockable=True))
        s.flush()

    with get_session() as s:
        inv = _issue_invoice(s)
        inv_id = inv.id

    with get_session() as s:
        d = build_einvoice_dict(s, inv_id)
        assert "-SVCID007-" in d["irn"]            # service id wins
        assert d["supplier"]["tin"] == "TIN-555"   # real TIN preferred over VAT
        assert d["supplier"]["firs_service_id"] == "SVCID007"


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
