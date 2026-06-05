"""Withholding Tax Credit Note PDF — FIRS Form WHT-002 layout.

For a supplier and a date range, enumerates the bills where we withheld tax
and renders a printable certificate the supplier can use to claim a WHT
credit. Tries the journal-line route first (account 2150 — WHT Payable) and
falls back to scanning bill lines whose tax_rate matches the configured
default WHT rate. This is needed because the seed posting in services.purchase
treats tax_rate as Input VAT — so a bill marked with WHT5 still ends up in
2120/1150, not 2150. We still want to issue the certificate, so we look at
the rate match as the source of truth.
"""
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
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Account,
    Bill,
    Company,
    DocStatus,
    JournalEntry,
    JournalLine,
    Supplier,
)


def _money(x: float, sym: str = "₦") -> str:
    if x is None:
        return "—"
    return f"{sym}{x:,.2f}"


def _collect_wht_rows(
    session: Session, supplier_id: int, *,
    period_start: date, period_end: date,
    wht_rate: float,
) -> list[dict]:
    """Return one dict per bill with WHT exposure in the period.

    Strategy: scan POSTED bills for the supplier in window. For each bill,
    sum journal-line debits/credits hitting the WHT receivable (1160) or
    payable (2150) account where source_id == bill.id. If that yields zero
    (because the seed posting routes WHT-rate lines to Input VAT), fall back
    to summing bill.lines where tax_rate is within ±0.001 of `wht_rate` and
    multiplying subtotal × tax_rate to derive the implied WHT amount.
    """
    wht_rec = session.execute(
        select(Account).where(Account.code == "1160")
    ).scalar_one_or_none()
    wht_pay = session.execute(
        select(Account).where(Account.code == "2150")
    ).scalar_one_or_none()
    wht_acct_ids = [a.id for a in (wht_rec, wht_pay) if a]

    bills = session.execute(
        select(Bill).where(
            Bill.supplier_id == supplier_id,
            Bill.status.in_([DocStatus.POSTED, DocStatus.PARTIAL, DocStatus.PAID]),
            Bill.bill_date >= period_start,
            Bill.bill_date <= period_end,
        ).order_by(Bill.bill_date, Bill.id)
    ).scalars().all()

    rows: list[dict] = []
    for bill in bills:
        wht_amount = 0.0
        if wht_acct_ids:
            q = (
                select(JournalLine)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .where(
                    JournalLine.account_id.in_(wht_acct_ids),
                    JournalEntry.status == DocStatus.POSTED,
                    JournalEntry.source_kind == "BILL",
                    JournalEntry.source_id == bill.id,
                )
            )
            for line in session.execute(q).scalars():
                # WHT receivable on debit (we suffered); payable on credit (we withheld).
                wht_amount += (line.debit + line.credit)

        wht_lines_subtotal = 0.0
        max_rate = 0.0
        if wht_amount == 0:
            for line in bill.lines:
                if abs(line.tax_rate - wht_rate) < 0.001 and line.tax_rate > 0:
                    wht_lines_subtotal += line.subtotal
                    if line.tax_rate > max_rate:
                        max_rate = line.tax_rate
            if wht_lines_subtotal > 0:
                wht_amount = round(wht_lines_subtotal * max_rate, 2)

        if wht_amount == 0:
            continue

        # Derive a gross + rate for the certificate row.
        if wht_lines_subtotal > 0:
            gross = wht_lines_subtotal
            rate = max_rate
        else:
            gross = bill.subtotal
            rate = round(wht_amount / gross, 4) if gross else wht_rate
        rows.append({
            "bill_date": bill.bill_date,
            "bill_ref": bill.number,
            "gross": round(gross, 2),
            "rate": rate,
            "wht": round(wht_amount, 2),
        })
    return rows


def write_wht_certificate_pdf(
    session: Session, supplier_id: int, *,
    period_start: date, period_end: date,
    out_path: str | Path,
    company: Optional[Company] = None,
) -> Path:
    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError(f"Supplier {supplier_id} not found.")

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
                        fontSize=16, leading=20,
                        textColor=colors.HexColor("#1F3864"))
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold",
                        fontSize=11, leading=14)
    small = ParagraphStyle("small", parent=base, fontSize=9, leading=11)
    right = ParagraphStyle("right", parent=base, alignment=2)

    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"WHT Certificate {supplier.code} {period_end.isoformat()}",
    )
    story: list = []

    # ---- Top banner ----
    serial = f"WHT-{supplier.code}-{period_end.strftime('%Y%m')}"
    banner = Table(
        [[Paragraph(
            "<b>WITHHOLDING TAX CREDIT NOTE</b><br/>"
            "<font size=9>Form FIRS-WHT-002</font>", h1,
        ),
          Paragraph(f"<b>Serial No.</b><br/>{serial}", right)]],
        colWidths=[110 * mm, 60 * mm],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F6FB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1F3864")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 6 * mm))

    # ---- Issuer (left) vs Beneficiary (right) ----
    issuer_lines = [Paragraph("<b>Issuer (Withholder)</b>", h2)]
    if company:
        issuer_lines.append(Paragraph(company.name, base))
        for line in (company.rc_number and f"RC: {company.rc_number}",
                     company.vat_number and f"TIN: {company.vat_number}",
                     company.address, company.email, company.phone):
            if line:
                issuer_lines.append(Paragraph(line, small))
    else:
        issuer_lines.append(Paragraph(settings.company_name, base))

    beneficiary_lines = [Paragraph("<b>Beneficiary (Supplier)</b>", h2),
                          Paragraph(supplier.name, base)]
    for line in (supplier.address, supplier.email, supplier.phone):
        if line:
            beneficiary_lines.append(Paragraph(line, small))

    parties = Table(
        [[issuer_lines, beneficiary_lines]],
        colWidths=[85 * mm, 85 * mm],
    )
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(parties)
    story.append(Spacer(1, 4 * mm))

    # ---- Period ----
    story.append(Paragraph(
        f"<b>Period Covered:</b> {period_start.isoformat()} → "
        f"{period_end.isoformat()}", base))
    story.append(Spacer(1, 4 * mm))

    # ---- Detail table ----
    detail_rows = _collect_wht_rows(
        session, supplier_id,
        period_start=period_start, period_end=period_end,
        wht_rate=settings.default_wht_rate,
    )
    header_row = ["Bill Date", "Bill Ref", "Gross Amount",
                  "WHT Rate", "WHT Amount"]
    table_data: list[list] = [header_row]
    total_gross = 0.0
    total_wht = 0.0
    for r in detail_rows:
        table_data.append([
            r["bill_date"].isoformat(),
            r["bill_ref"],
            _money(r["gross"], sym),
            f"{r['rate'] * 100:.2f}%",
            _money(r["wht"], sym),
        ])
        total_gross += r["gross"]
        total_wht += r["wht"]
    if not detail_rows:
        table_data.append(["—", "—", "—", "—", "—"])

    table_data.append([
        "", "TOTAL", _money(total_gross, sym), "",
        _money(total_wht, sym),
    ])

    detail = Table(
        table_data,
        colWidths=[26 * mm, 30 * mm, 36 * mm, 24 * mm, 36 * mm],
        repeatRows=1,
    )
    detail.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.white, colors.HexColor("#F4F6FB")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E5E7EB")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#0EA5A4")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(detail)
    story.append(Spacer(1, 12 * mm))

    # ---- Declaration + signature ----
    story.append(Paragraph(
        "I certify that the tax shown above has been withheld at source from "
        "payments due to the beneficiary named above, and remitted to the "
        "Federal Inland Revenue Service in accordance with the Companies "
        "Income Tax Act.", small))
    story.append(Spacer(1, 14 * mm))

    sig = Table(
        [["", ""],
         ["Authorized Signatory", "Date"]],
        colWidths=[100 * mm, 60 * mm],
    )
    sig.setStyle(TableStyle([
        ("LINEABOVE", (0, 1), (-1, 1), 0.5, colors.grey),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Oblique"),
        ("FONTSIZE", (0, 1), (-1, 1), 9),
        ("ALIGN", (0, 1), (-1, 1), "LEFT"),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ]))
    story.append(sig)

    doc.build(story)
    return out
