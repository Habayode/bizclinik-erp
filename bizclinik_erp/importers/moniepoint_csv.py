"""Moniepoint CSV statement importer.

A typical Moniepoint statement export has columns:
    Date, Description, Reference, Debit, Credit, Balance

Real exports drift — some headers say "Transaction Date" instead of "Date",
"Narration" instead of "Description", "Amount Debited" / "Amount Credited"
instead of "Debit" / "Credit". This parser is lenient: it normalises header
names and accepts a few common variants. Output is a uniform list of dicts
with the keys the recon service consumes.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Union

# Header normalisation map: lowercase / stripped header → canonical key.
_HEADER_ALIASES: dict[str, str] = {
    "date": "txn_date",
    "transaction date": "txn_date",
    "txn date": "txn_date",
    "trans date": "txn_date",       # GTBank
    "tran date": "txn_date",        # FBN / FirstBank
    "value date": "txn_date",       # Access / Zenith
    "effective date": "txn_date",   # Zenith
    "posting date": "txn_date",
    "booking date": "txn_date",
    "description": "description",
    "narration": "description",     # Access / GTBank
    "details": "description",
    "transaction details": "description",
    "particulars": "description",   # Zenith
    "remarks": "description",
    "memo": "description",
    "reference": "reference",
    "ref": "reference",
    "ref no": "reference",
    "reference number": "reference",
    "transaction reference": "reference",
    "transaction id": "reference",
    "instrument no": "reference",   # FBN
    "cheque no": "reference",
    "debit": "debit",
    "amount debited": "debit",
    "debit amount": "debit",
    "withdrawal": "debit",
    "withdrawals": "debit",
    "withdrawal amt": "debit",
    "money out": "debit",
    "dr": "debit",
    "credit": "credit",
    "amount credited": "credit",
    "credit amount": "credit",
    "deposit": "credit",
    "deposits": "credit",
    "deposit amt": "credit",
    "money in": "credit",
    "cr": "credit",
    "amount": "amount",             # single signed-amount column
    "transaction amount": "amount",
    "balance": "balance",
    "running balance": "balance",
    "available balance": "balance",
    "ledger balance": "balance",
}

# Date formats we'll try, in order of preference.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%m/%d/%Y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%Y/%m/%d",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def _parse_date(raw: str) -> date:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty date cell.")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    # Last-ditch: ISO fragments.
    try:
        return date.fromisoformat(raw[:10])
    except Exception as exc:
        raise ValueError(f"Could not parse date {raw!r}.") from exc


def _parse_money(raw: str) -> float:
    """Tolerant money parser. Strips ₦ / commas / quotes / whitespace."""
    if raw is None:
        return 0.0
    s = str(raw).strip()
    if not s:
        return 0.0
    # Bracketed negatives "(1,234.56)" → "-1234.56"
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    for ch in ("₦", "NGN", "N", "$", ",", " "):
        s = s.replace(ch, "")
    if not s or s == "-":
        return 0.0
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if negative else v


def _normalise_header(name: str) -> str:
    key = (name or "").strip().lower().replace("_", " ")
    return _HEADER_ALIASES.get(key, key)


def _load_rows(source: Union[bytes, str, Path]) -> Iterable[dict]:
    """Accept bytes, str CSV text, or path. Yield raw row dicts."""
    if isinstance(source, (bytes, bytearray)):
        text = source.decode("utf-8-sig", errors="replace")
    elif isinstance(source, Path) or (isinstance(source, str) and "\n" not in source
                                       and Path(source).exists()):
        text = Path(source).read_text(encoding="utf-8-sig", errors="replace")
    else:
        text = str(source)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    mapping = {orig: _normalise_header(orig) for orig in reader.fieldnames}
    out = []
    for raw in reader:
        out.append({mapping[k]: v for k, v in raw.items() if k in mapping})
    return out


def parse_moniepoint_csv(source: Union[bytes, str, Path]) -> list[dict]:
    """Parse a Moniepoint-style CSV into a uniform list of dicts.

    Returns rows shaped:
        {
            "txn_date":    date,
            "description": str,
            "amount":      float,    # +deposit, -withdrawal
            "reference":   str,
        }

    A row that has both debit and credit columns becomes a single signed
    amount: credit − debit. Rows with no usable date or zero amount are
    skipped silently — those are usually totals / header bands the bank
    sticks at the bottom of the file.
    """
    rows = _load_rows(source)
    out: list[dict] = []
    for raw in rows:
        # Skip totals rows / blank lines.
        date_cell = raw.get("txn_date", "")
        if not date_cell or not str(date_cell).strip():
            continue
        try:
            d = _parse_date(date_cell)
        except ValueError:
            continue
        debit = _parse_money(raw.get("debit", ""))
        credit = _parse_money(raw.get("credit", ""))
        amount = round(credit - debit, 2)
        if amount == 0.0:
            # Some statements put the entire amount in a single "Amount"
            # column with sign. Tolerate that one extra case.
            amt_alt = _parse_money(raw.get("amount", ""))
            if amt_alt == 0.0:
                continue
            amount = round(amt_alt, 2)
        out.append({
            "txn_date": d,
            "description": (raw.get("description") or "").strip(),
            "amount": amount,
            "reference": (raw.get("reference") or "").strip(),
        })
    return out
