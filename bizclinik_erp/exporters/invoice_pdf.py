"""PDF invoice generator (reportlab). Reads a SalesInvoice and emits a
printable A4 invoice with company header, line items, totals, and notes."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Company, SalesInvoice


def _money(x: float, sym: str = "₦") -> str:
    return f"{sym}{x:,.2f}"


def write_invoice_pdf(
    session: Session, invoice_id: int, out_path: str | Path,
    *, company: Optional[Company] = None,
) -> Path:
    inv = session.get(SalesInvoice, invoice_id)
    if not inv:
        raise ValueError(f"Invoice {invoice_id} not found.")
    settings = get_settings()
    company = company or session.query(Company).first()

    out = Path(out_path)
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontName="Helvetica",
                          fontSize=10, leading=12)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold",
                        fontSize=22, leading=26, textColor=colors.HexColor("#1F3864"))
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold",
                        fontSize=11, leading=14)
    small = ParagraphStyle("small", parent=base, fontSize=9, leading=11)
    right = ParagraphStyle("right", parent=base, alignment=2)

    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Invoice {inv.number}",
    )
    story: list = []

    # Header — INVOICE title + company info on left, invoice meta on right.
    company_block = []
    if company:
        company_block += [Paragraph(company.name, h2)]
        for line in (company.address, company.email, company.phone,
                     company.rc_number, (f"VAT: {company.vat_number}" if company.vat_number else None)):
            if line:
                company_block.append(Paragraph(line, small))
    else:
        company_block.append(Paragraph(settings.company_name, h2))
    invoice_meta = [
        Paragraph("INVOICE", h1),
        Paragraph(f"<b>No.</b> {inv.number}", right),
        Paragraph(f"<b>Date:</b> {inv.invoice_date.isoformat()}", right),
    ]
    if inv.due_date:
        invoice_meta.append(Paragraph(f"<b>Due:</b> {inv.due_date.isoformat()}", right))

    header = Table([[company_block, invoice_meta]], colWidths=[100 * mm, 65 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 6 * mm))

    # Bill-to
    bill_to = []
    if inv.customer:
        bill_to.append(Paragraph(f"<b>Bill To:</b> {inv.customer.name}", base))
        for line in (inv.customer.address, inv.customer.email, inv.customer.phone):
            if line:
                bill_to.append(Paragraph(line, small))
    story.extend(bill_to)
    story.append(Spacer(1, 4 * mm))

    # Lines
    header_row = ["S/N", "Description", "Qty", "Rate", "Tax %", "Tax", "Total"]
    rows = [header_row]
    for i, line in enumerate(inv.lines, 1):
        rows.append([
            str(i), line.description, f"{line.qty:,.2f}",
            _money(line.unit_price, settings.currency_symbol),
            f"{line.tax_rate * 100:.1f}%",
            _money(line.tax_amount, settings.currency_symbol),
            _money(line.subtotal + line.tax_amount, settings.currency_symbol),
        ])
    items = Table(rows, colWidths=[10 * mm, 70 * mm, 18 * mm, 25 * mm,
                                    15 * mm, 22 * mm, 30 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F4F6FB")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#1F3864")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(items)
    story.append(Spacer(1, 4 * mm))

    # Totals
    totals = [
        ["Subtotal", _money(inv.subtotal, settings.currency_symbol)],
        ["VAT", _money(inv.tax_total, settings.currency_symbol)],
        ["Grand Total", _money(inv.grand_total, settings.currency_symbol)],
    ]
    tot_table = Table(totals, colWidths=[45 * mm, 35 * mm], hAlign="RIGHT")
    tot_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#1F3864")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tot_table)

    if inv.notes:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("<b>Notes</b>", h2))
        story.append(Paragraph(inv.notes, base))

    # Footer
    story.append(Spacer(1, 12 * mm))
    footer = Table([["Company Signature", "Customer Signature"]],
                   colWidths=[80 * mm, 80 * mm])
    footer.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Oblique"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(footer)

    doc.build(story)
    return out
