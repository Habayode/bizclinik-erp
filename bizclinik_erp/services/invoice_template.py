"""Per-tenant invoice template settings.

A single ``InvoiceTemplate`` row per tenant DB holds branding for that tenant's
invoice PDFs. ``get_or_create`` is the only accessor the exporter needs;
``update`` powers the Settings UI.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InvoiceTemplate

_STYLES = {"classic", "modern", "minimal"}
_DEFAULT_ACCENT = "#1F3864"


def get_or_create(session: Session) -> InvoiceTemplate:
    tpl = session.execute(select(InvoiceTemplate)).scalars().first()
    if tpl is None:
        tpl = InvoiceTemplate()
        session.add(tpl)
        session.flush()
    return tpl


def _norm_hex(color: Optional[str]) -> str:
    c = (color or "").strip()
    if not c:
        return _DEFAULT_ACCENT
    if not c.startswith("#"):
        c = "#" + c
    # Accept #RGB or #RRGGBB; fall back to default if malformed.
    body = c[1:]
    if len(body) in (3, 6) and all(ch in "0123456789abcdefABCDEF" for ch in body):
        return c.upper()
    return _DEFAULT_ACCENT


def update(
    session: Session, *,
    accent_color: Optional[str] = None,
    template_style: Optional[str] = None,
    payment_instructions: Optional[str] = None,
    thank_you_note: Optional[str] = None,
    footer_note: Optional[str] = None,
    logo: Optional[bytes] = None,
    logo_mime: Optional[str] = None,
    clear_logo: bool = False,
) -> InvoiceTemplate:
    """Update template fields. Only provided (non-None) fields change. Pass
    ``clear_logo=True`` to remove an existing logo."""
    tpl = get_or_create(session)
    if accent_color is not None:
        tpl.accent_color = _norm_hex(accent_color)
    if template_style is not None:
        s = template_style.strip().lower()
        tpl.template_style = s if s in _STYLES else "classic"
    if payment_instructions is not None:
        tpl.payment_instructions = payment_instructions.strip() or None
    if thank_you_note is not None:
        tpl.thank_you_note = thank_you_note.strip()[:255] or None
    if footer_note is not None:
        tpl.footer_note = footer_note.strip()[:255] or None
    if clear_logo:
        tpl.logo = None
        tpl.logo_mime = None
    elif logo is not None:
        tpl.logo = logo
        tpl.logo_mime = logo_mime or "image/png"
    tpl.updated_at = datetime.utcnow()
    session.flush()
    return tpl
