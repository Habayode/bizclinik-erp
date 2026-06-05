"""Bank-agnostic statement parser.

Nigerian bank CSV exports vary in headers (GTBank, Access, Zenith, FBN,
Moniepoint, UBA, Kuda, OPay, …) but share the same shape: a date, a narration,
debit/credit (or a single signed amount), and a running balance. The underlying
parser (importers.moniepoint_csv) normalises a broad set of header aliases and
date/money formats, so one lenient parser handles them all — adding a new bank
is usually just adding a header alias, not a new parser.

Use ``parse_bank_statement(source)`` for any bank's CSV. ``SUPPORTED_BANKS`` is
a non-exhaustive list of banks known to import cleanly (mostly for the UI
dropdown); unknown banks still parse if their headers are conventional.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from .moniepoint_csv import parse_moniepoint_csv as _parse

# For UI hints / dropdowns. The parser is not limited to these.
SUPPORTED_BANKS = [
    "Auto-detect",
    "Moniepoint",
    "GTBank",
    "Access Bank",
    "Zenith Bank",
    "First Bank (FBN)",
    "UBA",
    "Kuda",
    "OPay",
    "Other / generic CSV",
]


def parse_bank_statement(source: Union[bytes, str, Path], *, bank: str | None = None) -> list[dict]:
    """Parse any bank's CSV statement into uniform rows.

    Returns a list of ``{"txn_date": date, "description": str, "amount": float,
    "reference": str}`` (amount is signed: +credit, −debit) — exactly the shape
    ``services.recon.import_statement_lines`` consumes. ``bank`` is accepted for
    forward-compat / UI labelling but the parser is format-driven, not
    bank-specific.
    """
    return _parse(source)
