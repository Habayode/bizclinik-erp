"""Customer statement of account helpers.

Walks the journal_line rows for a customer's AR account to produce the data
backing both the Streamlit Statements page and the PDF exporter. All numbers
are sourced from posted GL — so the SOA is always consistent with the books.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    Customer,
    DocStatus,
    JournalEntry,
    JournalLine,
    SalesInvoice,
)


def _customer_ar_account_id(session: Session, customer: Customer) -> int:
    """Resolve the AR account for a customer (custom override or default 1130)."""
    if customer.receivable_account_id:
        return customer.receivable_account_id
    default = session.execute(
        select(Account).where(Account.code == "1130")
    ).scalar_one_or_none()
    if not default:
        raise RuntimeError("Default AR account 1130 missing. Seed defaults first.")
    return default.id


def customer_opening_balance(
    session: Session, customer_id: int, *, as_of: date,
) -> float:
    """Customer's outstanding AR balance up to (and including) `as_of`.

    Positive = customer owes us (DR balance on the AR account, restricted to
    journal lines tagged with this customer).
    """
    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")
    ar_id = _customer_ar_account_id(session, customer)
    q = (
        select(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == ar_id,
            JournalEntry.status == DocStatus.POSTED,
            JournalEntry.entry_date <= as_of,
            or_(
                JournalLine.customer_id == customer_id,
                # Fall back to source linkage if customer_id wasn't tagged.
                and_(
                    JournalLine.customer_id.is_(None),
                    JournalEntry.source_kind.in_(("INVOICE", "RECEIPT")),
                ),
            ),
        )
    )
    total_dr = 0.0
    total_cr = 0.0
    for line in session.execute(q).scalars():
        # When customer_id is null we need a stricter membership check.
        if line.customer_id is None:
            # Confirm via source: invoice or receipt for this customer.
            entry = session.get(JournalEntry, line.entry_id)
            if entry and entry.source_kind == "INVOICE":
                inv = session.get(SalesInvoice, entry.source_id)
                if not inv or inv.customer_id != customer_id:
                    continue
            elif entry and entry.source_kind == "RECEIPT":
                from ..models import Receipt
                r = session.get(Receipt, entry.source_id)
                if not r or r.customer_id != customer_id:
                    continue
            else:
                continue
        total_dr += line.debit
        total_cr += line.credit
    return round(total_dr - total_cr, 2)


def customer_outstanding(
    session: Session, customer_id: int, *, as_of: date,
) -> float:
    """Same as opening balance — what the customer owes as of a given date."""
    return customer_opening_balance(session, customer_id, as_of=as_of)


def customer_ledger(
    session: Session, customer_id: int, *,
    period_start: date, period_end: date,
) -> list[dict]:
    """Detail rows for the customer's AR sub-ledger in a window.

    Returns one dict per posting line: {date, entry_no, memo, debit, credit,
    running_balance}. Running balance starts from the opening balance carried
    in from before `period_start` and increases by DR-CR per line.
    """
    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")
    ar_id = _customer_ar_account_id(session, customer)

    opening = customer_opening_balance(
        session, customer_id,
        as_of=period_start - timedelta(days=1),
    )

    q = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == ar_id,
            JournalEntry.status == DocStatus.POSTED,
            JournalEntry.entry_date >= period_start,
            JournalEntry.entry_date <= period_end,
        )
        .order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id)
    )

    rows: list[dict] = []
    running = opening
    for line, entry in session.execute(q):
        # Filter to this customer's lines (either tagged or via source).
        if line.customer_id is not None:
            if line.customer_id != customer_id:
                continue
        else:
            if entry.source_kind == "INVOICE":
                inv = session.get(SalesInvoice, entry.source_id)
                if not inv or inv.customer_id != customer_id:
                    continue
            elif entry.source_kind == "RECEIPT":
                from ..models import Receipt
                r = session.get(Receipt, entry.source_id)
                if not r or r.customer_id != customer_id:
                    continue
            else:
                continue
        running += (line.debit - line.credit)
        rows.append({
            "date": entry.entry_date,
            "entry_no": entry.entry_no,
            "memo": line.memo or entry.memo or "",
            "debit": round(line.debit, 2),
            "credit": round(line.credit, 2),
            "running_balance": round(running, 2),
        })
    return rows


# --------------------------------------------------------------------------- #
# Email a statement PDF to the customer                                        #
# --------------------------------------------------------------------------- #

def email_statement(
    session: Session, customer_id: int, *,
    period_start: date, period_end: date,
    to_addr: Optional[str] = None,
) -> dict:
    """Render the customer's statement PDF and email it as an attachment.

    Recipient defaults to the customer's email on file. Returns a status dict:
    ``{"sent": bool, "to": str|None, "reason": str|None}``. Never raises for a
    missing recipient or unconfigured SMTP — it reports the reason so callers
    (UI/API) can show a friendly message.
    """
    import tempfile
    from pathlib import Path

    from ..exporters.customer_statement_pdf import write_customer_statement_pdf
    from . import notifications

    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")

    recipient = (to_addr or customer.email or "").strip()
    if not recipient:
        return {"sent": False, "to": None,
                "reason": "No email address on file for this customer."}
    if not notifications.smtp_configured():
        return {"sent": False, "to": recipient,
                "reason": "SMTP is not configured (set SMTP_HOST/USER/PASS/FROM)."}

    outstanding = customer_outstanding(session, customer_id, as_of=period_end)
    tmp_dir = Path(tempfile.mkdtemp(prefix="bizclinik_soa_"))
    fname = f"statement_{customer.code}_{period_end.isoformat()}.pdf"
    pdf_path = tmp_dir / fname
    write_customer_statement_pdf(
        session, customer_id, period_start=period_start, period_end=period_end,
        out_path=pdf_path)

    subject = f"Statement of Account — {period_start.isoformat()} to {period_end.isoformat()}"
    body = (
        f"Dear {customer.name},\n\n"
        f"Please find attached your statement of account for the period "
        f"{period_start.isoformat()} to {period_end.isoformat()}.\n\n"
        f"Outstanding balance as at {period_end.isoformat()}: {outstanding:,.2f}\n\n"
        f"Thank you for your business.\n"
    )
    ok = notifications.send_email_with_attachment(
        to_addr=recipient, subject=subject, body_text=body,
        attachment_path=str(pdf_path), attachment_name=fname)

    try:
        pdf_path.unlink(missing_ok=True)
        tmp_dir.rmdir()
    except Exception:
        pass

    return {"sent": ok, "to": recipient,
            "reason": None if ok else "SMTP send failed (check server logs/credentials)."}
