"""FIRS e-invoice submission tracking.

One row per generated FIRS e-invoice. Holds the IRN, the full JSON payload
(stored as TEXT), the compact QR payload, and a lifecycle status that moves
GENERATED → SUBMITTED → ACCEPTED/REJECTED as the document is filed with the
FIRS Merchant Buyer Solution.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class EInvoiceStatus(str, enum.Enum):
    GENERATED = "GENERATED"   # payload built locally, not yet filed
    SUBMITTED = "SUBMITTED"   # sent to FIRS MBS
    ACCEPTED = "ACCEPTED"     # MBS countersigned (CSID issued)
    REJECTED = "REJECTED"     # MBS rejected the document


class EInvoiceSubmission(Base):
    __tablename__ = "einvoice_submission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("sales_invoice.id"), nullable=False, index=True
    )
    irn: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[EInvoiceStatus] = mapped_column(
        Enum(EInvoiceStatus), default=EInvoiceStatus.GENERATED, nullable=False
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    qr_payload: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    invoice = relationship("SalesInvoice")
