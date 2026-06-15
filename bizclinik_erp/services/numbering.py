"""Document numbering: next sequential number per prefix + year.

Backed by an atomic per-(kind, year) counter (models.DocCounter): next_number()
does an ``UPDATE doc_counter SET value = value + 1 RETURNING value`` under the
row lock, so two concurrent posts cannot read the same max() and generate the
same document number (the previous max()+1 approach raced on Postgres/REST).
The counter is seeded once from any pre-existing documents so it never reissues
a number that legacy data already used.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    Bill,
    DocCounter,
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


def _seed_from_existing(session: Session, model, col, key: str, prefix: str) -> None:
    """One-time: create the counter row, starting from the highest serial any
    existing document already uses (0 if none). Race-safe via a savepoint —
    if another transaction seeds it first, we simply roll the savepoint back."""
    last = session.execute(
        select(func.max(getattr(model, col)))
        .where(getattr(model, col).like(f"{prefix}%"))
    ).scalar_one_or_none()
    start = 0
    if last:
        try:
            start = int(str(last).split("-")[-1])
        except ValueError:
            start = 0
    sp = session.begin_nested()
    try:
        session.add(DocCounter(key=key, value=start))
        session.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()   # another writer seeded it concurrently — fine


def next_number(session: Session, doc_kind: str, on: date | None = None) -> str:
    """Return the next unused number for the given doc kind.

    Format: '{KIND}-{YYYY}-{0001}'. The 4-digit serial restarts each year.
    Allocation is atomic (see module docstring) so it is safe under concurrent
    posts on the same tenant.
    """
    if doc_kind not in _DOC_MODEL:
        raise ValueError(f"Unknown doc kind: {doc_kind}")
    model, col = _DOC_MODEL[doc_kind]
    year = (on or date.today()).year
    prefix = f"{doc_kind}-{year}-"
    key = f"{doc_kind}-{year}"

    # Atomic increment; the row lock serialises concurrent allocators.
    serial = session.execute(
        update(DocCounter).where(DocCounter.key == key)
        .values(value=DocCounter.value + 1).returning(DocCounter.value)
    ).scalar_one_or_none()
    if serial is None:
        # First number for this (kind, year) — seed from any legacy docs, retry.
        _seed_from_existing(session, model, col, key, prefix)
        serial = session.execute(
            update(DocCounter).where(DocCounter.key == key)
            .values(value=DocCounter.value + 1).returning(DocCounter.value)
        ).scalar_one()
    return f"{prefix}{serial:04d}"
