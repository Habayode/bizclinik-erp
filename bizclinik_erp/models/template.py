"""Per-tenant invoice branding/template.

Single-row settings table (like Company) that lives in each tenant's own DB, so
every tenant can brand their invoices — accent colour, logo, payment
instructions, thank-you note, and a layout style — without affecting others.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class InvoiceTemplate(Base):
    __tablename__ = "invoice_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Brand accent (hex) used for the title, table header, and rules.
    accent_color: Mapped[str] = mapped_column(String(9), default="#1F3864")
    # Layout style: "classic" | "modern" | "minimal".
    template_style: Mapped[str] = mapped_column(String(16), default="classic")
    # Optional logo bytes + mime, rendered top-left if present.
    logo: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    logo_mime: Mapped[Optional[str]] = mapped_column(String(64))
    # Free-text blocks shown on the invoice.
    payment_instructions: Mapped[Optional[str]] = mapped_column(Text)
    thank_you_note: Mapped[Optional[str]] = mapped_column(String(255))
    footer_note: Mapped[Optional[str]] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
