"""Tax: VAT return, WHT certificate generation."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account
from .ledger import account_balance


def vat_return(session: Session, *, period_start: date, period_end: date) -> dict:
    """Net VAT position for a period.

    Output VAT (sales) - Input VAT (purchases) = net VAT payable.
    Pulls from account codes 2120 (Output) and 1150 (Input).
    """
    out_acct = session.execute(
        select(Account).where(Account.code == "2120")
    ).scalar_one_or_none()
    in_acct = session.execute(
        select(Account).where(Account.code == "1150")
    ).scalar_one_or_none()
    output_vat = account_balance(session, out_acct.id,
                                  period_start=period_start, as_of=period_end) if out_acct else 0
    input_vat = account_balance(session, in_acct.id,
                                 period_start=period_start, as_of=period_end) if in_acct else 0
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "output_vat": output_vat,
        "input_vat": input_vat,
        "net_payable": round(output_vat - input_vat, 2),
    }


def wht_position(session: Session, *, period_start: date, period_end: date) -> dict:
    """Net WHT position: WHT receivable (you suffered) vs WHT payable (you withheld)."""
    rec_acct = session.execute(
        select(Account).where(Account.code == "1160")
    ).scalar_one_or_none()
    pay_acct = session.execute(
        select(Account).where(Account.code == "2150")
    ).scalar_one_or_none()
    wht_rec = account_balance(session, rec_acct.id,
                               period_start=period_start, as_of=period_end) if rec_acct else 0
    wht_pay = account_balance(session, pay_acct.id,
                               period_start=period_start, as_of=period_end) if pay_acct else 0
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "wht_suffered_receivable": wht_rec,
        "wht_withheld_payable": wht_pay,
    }
