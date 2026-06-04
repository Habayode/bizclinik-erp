"""Document numbering: next sequential number per prefix + year."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Bill,
    JournalEntry,
    Payment,
    PayrollRun,
    PurchaseOrder,
    Quotation,
    Receipt,
    SalesInvoice,
    SalesOrder,
)


_DOC_MODEL = {
    "JE": (JournalEntry, "entry_no"),
    "QUO": (Quotation, "number"),
    "SO": (SalesOrder, "number"),
    "INV": (SalesInvoice, "number"),
    "RCT": (Receipt, "number"),
    "PO": (PurchaseOrder, "number"),
    "BIL": (Bill, "number"),
    "PAY": (Payment, "number"),
    "PR": (PayrollRun, "number"),
}


def next_number(session: Session, doc_kind: str, on: date | None = None) -> str:
    """Return the next unused number for the given doc kind.

    Format: '{KIND}-{YYYY}-{0001}'. The 4-digit serial restarts each year.
    """
    if doc_kind not in _DOC_MODEL:
        raise ValueError(f"Unknown doc kind: {doc_kind}")
    model, col = _DOC_MODEL[doc_kind]
    year = (on or date.today()).year
    prefix = f"{doc_kind}-{year}-"
    last = session.execute(
        select(func.max(getattr(model, col))).where(getattr(model, col).like(f"{prefix}%"))
    ).scalar_one_or_none()
    if last:
        try:
            serial = int(last.split("-")[-1]) + 1
        except ValueError:
            serial = 1
    else:
        serial = 1
    return f"{prefix}{serial:04d}"
