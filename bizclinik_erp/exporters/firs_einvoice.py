"""FIRS e-invoice payload builder.

Nigeria's FIRS e-invoicing mandate (2026) expects a structured JSON document
submitted to the Merchant Buyer Solution (MBS). The exact schema is still
evolving, so this module produces a clean, well-structured payload that mirrors
the BIS Billing 3.0 / FIRS MBS field model: a supplier block, a customer block,
line items with per-line VAT, a tax summary, and a legal monetary total.

The payload is built purely from a SalesInvoice and the Company record — no
network calls happen here. Persistence + status tracking lives in
services.firs; this module is the pure transform.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Company, SalesInvoice


# Until the business is onboarded to the FIRS Merchant Buyer Solution, the
# generated document is a DRAFT: the CSID and QR are placeholders with no legal
# standing. This notice is embedded in the payload so it can never be mistaken
# for a FIRS-cleared invoice.
DRAFT_CSID = "PENDING-CSID"
DRAFT_NOTICE = (
    "DRAFT — not yet transmitted to the FIRS Merchant Buyer Solution. "
    "The CSID and QR code are placeholders and carry no legal validity until "
    "FIRS countersigns the invoice."
)


def _clean_token(s: Optional[str]) -> str:
    """Uppercase alphanumeric token for use inside an IRN segment.

    Strips spaces and punctuation so e.g. an RC number 'RC 8229227' becomes
    'RC8229227' — IRNs must be continuous alphanumeric tokens with no spaces.
    """
    return re.sub(r"[^A-Za-z0-9]", "", (s or "")).upper()


def _supplier_tin(company: Optional[Company]) -> Optional[str]:
    """Supplier's Tax Identification Number.

    The TIN is a distinct identifier from the CAC RC number; we never fall back
    to the RC number here (doing so mislabels the RC as a TIN). VAT number is an
    acceptable stand-in only because Nigerian VAT registration is TIN-based.
    Returns None when no genuine tax id is on file.
    """
    if not company:
        return None
    tin = (getattr(company, "tin", None) or company.vat_number or "").strip()
    return tin or None


def _irn_party_segment(company: Optional[Company]) -> str:
    """Middle segment of the IRN.

    FIRS assigns each onboarded supplier an 8-character Service ID that belongs
    here. Until then we fall back to a cleaned TIN, then the cleaned RC number,
    so a draft IRN is still deterministic and space-free.
    """
    if company is not None:
        for candidate in (getattr(company, "firs_service_id", None),
                          _supplier_tin(company), company.rc_number):
            tok = _clean_token(candidate)
            if tok:
                return tok
    return "UNKNOWN"


def _round2(x: float) -> float:
    return round(float(x or 0.0), 2)


def build_irn(invoice_number: str, party_segment: str, issue_date: date) -> str:
    """Deterministic Invoice Reference Number: {number}-{party}-{yyyymmdd}.

    Every segment is cleaned to alphanumeric so the IRN never contains spaces
    or punctuation that would clash with the '-' segment separators.
    """
    num = _clean_token(invoice_number)
    party = _clean_token(party_segment) or "UNKNOWN"
    return f"{num}-{party}-{issue_date.strftime('%Y%m%d')}"


def build_einvoice_dict(session: Session, invoice_id: int) -> dict:
    """Build a FIRS-style e-invoice payload for one SalesInvoice.

    Returns a plain dict (JSON-serialisable). Raises ValueError if the invoice
    does not exist.
    """
    inv = session.get(SalesInvoice, invoice_id)
    if not inv:
        raise ValueError(f"Invoice {invoice_id} not found.")

    settings = get_settings()
    company = session.query(Company).first()
    customer = inv.customer

    supplier_tin = _supplier_tin(company)
    irn = build_irn(inv.number, _irn_party_segment(company), inv.invoice_date)

    line_items: list[dict] = []
    for i, line in enumerate(inv.lines, start=1):
        line_ext = _round2(line.subtotal)
        line_vat = _round2(line.tax_amount)
        line_items.append({
            "id": i,
            "description": line.description,
            "quantity": _round2(line.qty),
            "unit_price": _round2(line.unit_price),
            "line_extension_amount": line_ext,
            "vat": {
                "rate_percent": _round2(line.tax_rate * 100),
                "amount": line_vat,
            },
            "line_total": _round2(line_ext + line_vat),
        })

    taxable_base = _round2(inv.subtotal)
    total_vat = _round2(inv.tax_total)
    grand_total = _round2(inv.grand_total)

    return {
        "document_status": "DRAFT",
        "firs_notice": DRAFT_NOTICE,
        "irn": irn,
        "csid": DRAFT_CSID,  # placeholder until MBS countersigns
        "invoice_number": inv.number,
        "issue_date": inv.invoice_date.isoformat(),
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "currency": settings.currency_code,
        "supplier": {
            "name": company.name if company else settings.company_name,
            "tin": supplier_tin,
            "rc_number": company.rc_number if company else None,
            "vat_number": company.vat_number if company else None,
            "firs_service_id": getattr(company, "firs_service_id", None) if company else None,
            "address": company.address if company else None,
            "email": company.email if company else None,
            "phone": company.phone if company else None,
        },
        "customer": {
            "name": customer.name if customer else None,
            "tin": None,  # Customer model carries no TIN field yet
            "address": customer.address if customer else None,
            "email": customer.email if customer else None,
            "phone": customer.phone if customer else None,
        },
        "line_items": line_items,
        "tax_summary": {
            "taxable_base": taxable_base,
            "total_vat": total_vat,
        },
        "legal_monetary_total": {
            "line_extension_amount": taxable_base,
            "tax_exclusive_amount": taxable_base,
            "tax_inclusive_amount": grand_total,
            "payable_amount": grand_total,
        },
    }


def write_einvoice_json(session: Session, invoice_id: int, out_path: str | Path) -> Path:
    """Write the e-invoice dict as pretty UTF-8 JSON. Refuses to overwrite."""
    out = Path(out_path)
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    d = build_einvoice_dict(session, invoice_id)
    out.write_text(
        json.dumps(d, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


def einvoice_qr_payload(d: dict) -> str:
    """Compact QR string: IRN|date|supplier_tin|total|vat.

    Suitable for embedding in a QR code on the printed invoice so a verifier
    can read the key facts without parsing the full JSON.
    """
    irn = d.get("irn", "")
    issue_date = d.get("issue_date", "")
    supplier_tin = d.get("supplier", {}).get("tin") or ""
    total = d.get("legal_monetary_total", {}).get("payable_amount", 0.0)
    vat = d.get("tax_summary", {}).get("total_vat", 0.0)
    return f"{irn}|{issue_date}|{supplier_tin}|{total:.2f}|{vat:.2f}"
