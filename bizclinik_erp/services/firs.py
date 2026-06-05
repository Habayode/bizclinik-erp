"""FIRS e-invoice service.

Bridges the pure payload builder (exporters.firs_einvoice) and the persistence
layer (models.einvoice). `generate_for_invoice` builds the e-invoice dict,
derives the IRN + QR payload, and persists an EInvoiceSubmission row in the
GENERATED state, ready for later submission to the FIRS MBS.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..exporters.firs_einvoice import build_einvoice_dict, einvoice_qr_payload
from ..models import EInvoiceStatus, EInvoiceSubmission


def generate_for_invoice(session: Session, invoice_id: int) -> EInvoiceSubmission:
    """Build, serialise, and persist a FIRS e-invoice for one SalesInvoice.

    Returns the persisted EInvoiceSubmission (status GENERATED). Raises
    ValueError if the invoice does not exist.
    """
    d = build_einvoice_dict(session, invoice_id)
    qr_payload = einvoice_qr_payload(d)

    submission = EInvoiceSubmission(
        invoice_id=invoice_id,
        irn=d["irn"],
        status=EInvoiceStatus.GENERATED,
        payload_json=json.dumps(d, ensure_ascii=False, indent=2),
        qr_payload=qr_payload,
    )
    session.add(submission)
    session.flush()
    return submission


def list_submissions(session: Session) -> list[EInvoiceSubmission]:
    """All e-invoice submissions, newest first."""
    return list(
        session.execute(
            select(EInvoiceSubmission).order_by(EInvoiceSubmission.id.desc())
        ).scalars()
    )
