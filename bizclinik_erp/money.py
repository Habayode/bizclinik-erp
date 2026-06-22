"""Money quantization helpers.

Monetary columns are stored as NUMERIC(18,2) (see db.Money) — exact decimal on
Postgres — with asdecimal=False so the ORM still hands callers plain floats. All
*summation* of money also routes through Decimal here so we never accumulate the
sub-cent float drift that ``round(sum([...]), 2)`` can produce across many lines.
Values come back as float so callers and the ORM are unchanged.

    msum(values)  -> exact 2dp sum of an iterable of money values
    money(x)      -> a single value quantized to 2dp (half-up)
    to_dec(x)     -> Decimal view of a money value (None -> 0)
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

CENTS = Decimal("0.01")


def to_dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    # str() avoids pulling in the binary-float representation error.
    return Decimal(str(x))


def money(x) -> float:
    """Quantize a single monetary value to 2 decimal places, rounding half-up
    (the convention for cash), returned as float."""
    return float(to_dec(x).quantize(CENTS, rounding=ROUND_HALF_UP))


def msum(values: Iterable) -> float:
    """Sum monetary values exactly in Decimal, then quantize to 2dp. Drop-in
    replacement for ``round(sum(values), 2)`` that does not drift."""
    total = Decimal("0")
    for v in values:
        total += to_dec(v)
    return float(total.quantize(CENTS, rounding=ROUND_HALF_UP))
