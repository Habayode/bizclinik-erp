"""Per-tenant invoice template: defaults, update, and branded PDF generation."""
from __future__ import annotations

import struct
import tempfile
import zlib
from datetime import date
from pathlib import Path

from sqlalchemy import select


def _png_bytes() -> bytes:
    """A minimal valid 1x1 PNG (so reportlab's Image can read it)."""
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xff\x00\x00"  # one red pixel + filter byte
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def test_template_defaults_created(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import invoice_template as it
    with get_session() as s:
        tpl = it.get_or_create(s)
        assert tpl.accent_color == "#1F3864"
        assert tpl.template_style == "classic"


def test_update_normalises_hex_and_style(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import invoice_template as it
    with get_session() as s:
        tpl = it.update(s, accent_color="ff8800", template_style="bogus",
                        thank_you_note="Thanks!", payment_instructions="Pay to X")
        assert tpl.accent_color == "#FF8800"     # '#' prepended, upper-cased
        assert tpl.template_style == "classic"   # invalid -> default
        assert tpl.thank_you_note == "Thanks!"
    # Bad hex falls back to default.
    with get_session() as s:
        tpl = it.update(s, accent_color="not-a-color")
        assert tpl.accent_color == "#1F3864"


def _seed_invoice(s):
    from bizclinik_erp.services import sales
    from bizclinik_erp.models import Customer, Product
    s.add(Customer(code="C1", name="Acme"))
    s.add(Product(sku="P1", name="Widget", standard_price=100,
                  standard_cost=40, is_stockable=False))
    s.flush()
    cust = s.execute(select(Customer)).scalar_one()
    prod = s.execute(select(Product)).scalar_one()
    return sales.issue_invoice(
        s, customer_id=cust.id, invoice_date=date(2026, 1, 10),
        lines=[sales.LineInput(product_id=prod.id, description="Widget",
                               qty=2, unit_price=100, tax_rate=0.075)]).id


def test_branded_pdf_builds(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import invoice_template as it
    from bizclinik_erp.exporters.invoice_pdf import write_invoice_pdf

    with get_session() as s:
        inv_id = _seed_invoice(s)
        it.update(s, accent_color="#0A7D33", payment_instructions="Bank: GTB 0123",
                  thank_you_note="We appreciate your business",
                  footer_note="Powered by BizClinik",
                  logo=_png_bytes(), logo_mime="image/png")

    out = Path(tempfile.mkdtemp()) / "inv.pdf"
    with get_session() as s:
        write_invoice_pdf(s, inv_id, out)
    data = out.read_bytes()
    assert data[:4] == b"%PDF"
    assert len(data) > 1000


def test_clear_logo(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import invoice_template as it
    with get_session() as s:
        it.update(s, logo=_png_bytes(), logo_mime="image/png")
    with get_session() as s:
        tpl = it.update(s, clear_logo=True)
        assert tpl.logo is None and tpl.logo_mime is None
