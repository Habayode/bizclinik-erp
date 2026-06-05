"""Customer Statement of Account PDF (reportlab).

Walks the customer's AR sub-ledger over a period and emits an A4 statement
matching the BizClinik brand (navy header #1F3864, teal accent #0EA5A4).
Includes opening + closing balance, aging buckets, and remit-to details.
"""
from __future__ import annotations

from datetime import date, timedelta
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
from ..models import BankAccount, Company, Customer
from ..services import reports as reports_svc
from ..services.customer_statement import (
    customer_ledger,
    customer_opening_balance,
)


def _money(x: float, sym: str = "₦") -> str:
    if x is None:
        return "—"
    return f"{sym}{x:,.2f}"


def write_customer_statement_pdf(
    session: Session, customer_id: int, *,
    period_start: date, period_end: date,
    out_path: str | Path,
    company: Optional[Company] = None,
) -> Path:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")

    settings = get_settings()
    company = company or session.query(Company).first()

    out = Path(out_path)
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)

    sym = settings.currency_symbol

    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontName="Helvetica",
                          fontSize=10, leading=12)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold",
                        fontSize=22, leading=26,
                        textColor=colors.HexColor("#1F3864"))
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold",
                        fontSize=11, leading=14)
    small = ParagraphStyle("small", parent=base, fontSize=9, leading=11)
    right = ParagraphStyle("right", parent=base, alignment=2)

    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Statement {customer.code} {period_end.isoformat()}",
    )
    story: list = []

    # ---- Header: company on left, STATEMENT meta on right ----
    company_block = []
    if company:
        company_block.append(Paragraph(company.name, h2))
        for line in (company.address, company.email, company.phone,
                     company.rc_number,
                     (f"VAT: {company.vat_number}" if company.vat_number else None)):
            if line:
                company_block.append(Paragraph(line, small))
    else:
        company_block.append(Paragraph(settings.company_name, h2))

    stmt_no = f"SOA-{customer.code}-{period_end.strftime('%Y%m')}"
    meta = [
        Paragraph("STATEMENT OF ACCOUNT", h1),
        Paragraph(f"<b>No.</b> {stmt_no}", right),
        Paragraph(
            f"<b>Period:</b> {period_start.isoformat()} → {period_end.isoformat()}",
            right,
        ),
    ]

    header = Table([[company_block, meta]], colWidths=[100 * mm, 70 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 6 * mm))

    # ---- Bill-to ----
    bill_to = [Paragraph(f"<b>Bill To:</b> {customer.name}", base)]
    for line in (customer.address, customer.email, customer.phone):
        if line:
            bill_to.append(Paragraph(line, small))
    story.extend(bill_to)
    story.append(Spacer(1, 4 * mm))

    # ---- Statement table ----
    opening = customer_opening_balance(
        session, customer_id,
        as_of=period_start - timedelta(days=1),
    )
    rows = customer_ledger(
        session, customer_id,
        period_start=period_start, period_end=period_end,
    )
    closing = rows[-1]["running_balance"] if rows else opening

    header_row = ["Date", "Reference", "Description",
                  "Debit", "Credit", "Balance"]
    table_data: list[list] = [header_row]
    table_data.append([
        period_start.isoformat(), "", "OPENING BALANCE",
        "", "", _money(opening, sym),
    ])
    for r in rows:
        memo = r["memo"] or ""
        if len(memo) > 48:
            memo = memo[:45] + "..."
        table_data.append([
            r["date"].isoformat(),
            r["entry_no"],
            memo,
            _money(r["debit"], sym) if r["debit"] else "",
            _money(r["credit"], sym) if r["credit"] else "",
            _money(r["running_balance"], sym),
        ])
    table_data.append([
        period_end.isoformat(), "", "CLOSING BALANCE",
        "", "", _money(closing, sym),
    ])

    items = Table(
        table_data,
        colWidths=[22 * mm, 24 * mm, 58 * mm, 24 * mm, 24 * mm, 26 * mm],
        repeatRows=1,
    )
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (2, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F4F6FB")]),
        # OPENING and CLOSING band rows.
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#E5E7EB")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E5E7EB")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#1F3864")),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#0EA5A4")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(items)
    story.append(Spacer(1, 6 * mm))

    # ---- Aging summary ----
    aging_rows = reports_svc.ar_aging(session, as_of=period_end)
    mine = next(
        (r for r in aging_rows if r["customer_id"] == customer_id),
        None,
    )
    aging_header = ["0-30", "31-60", "61-90", "90+", "Total"]
    if mine:
        aging_values = [
            _money(mine.get("0-30", 0.0), sym),
            _money(mine.get("31-60", 0.0), sym),
            _money(mine.get("61-90", 0.0), sym),
            _money(mine.get("90+", 0.0), sym),
            _money(mine.get("total", 0.0), sym),
        ]
    else:
        z = _money(0.0, sym)
        aging_values = [z, z, z, z, z]

    story.append(Paragraph("<b>Aging summary</b>", h2))
    aging_tbl = Table([aging_header, aging_values], colWidths=[32 * mm] * 5)
    aging_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0EA5A4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F4F6FB")),
    ]))
    story.append(aging_tbl)
    story.append(Spacer(1, 8 * mm))

    # ---- Remit-to footer ----
    bank = session.query(BankAccount).filter(
        BankAccount.is_active.is_(True)
    ).first()
    if bank:
        remit_text = (
            f"<b>Please remit to:</b> {bank.name}"
            + (f" — {bank.bank}" if bank.bank else "")
            + (f" — Acct {bank.account_number}" if bank.account_number else "")
        )
    else:
        remit_text = "<b>Please remit to:</b> (no active bank account configured)"
    story.append(Paragraph(remit_text, base))

    story.append(Spacer(1, 10 * mm))
    footer = Table([["Authorized Signature", "Customer Acknowledgement"]],
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
