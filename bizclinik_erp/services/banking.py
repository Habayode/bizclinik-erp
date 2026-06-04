"""Banking: standalone bank transactions, bank balances, simple reconcile.

For receipts/payments tied to invoices/bills the sales/purchase services do
the GL work. This module covers bank-direct transactions (transfers, charges,
interest) and the bank-statement reconciliation flow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    BankAccount,
    DocStatus,
    JournalEntry,
    JournalLine,
)
from .ledger import JELine, account_balance, post_journal


def bank_balance(session: Session, bank_account_id: int,
                 as_of: Optional[date] = None) -> float:
    """Current balance of the bank account's GL counterpart."""
    ba = session.get(BankAccount, bank_account_id)
    if not ba:
        return 0.0
    return account_balance(session, ba.gl_account_id, as_of=as_of) + (ba.opening_balance or 0.0)


def post_bank_charge(session: Session, *, bank_account_id: int, on: date,
                     amount: float, memo: str = "Bank charge") -> JournalEntry:
    """DR Bank Charges / CR Bank."""
    ba = session.get(BankAccount, bank_account_id)
    if not ba:
        raise ValueError(f"Bank account {bank_account_id} not found.")
    charges_acct = session.execute(
        select(Account).where(Account.code == "6500")
    ).scalar_one()
    return post_journal(session, on, memo, [
        JELine(account_id=charges_acct.id, debit=amount, memo=memo),
        JELine(account_id=ba.gl_account_id, credit=amount, memo=memo),
    ], source_kind="BANK", source_id=bank_account_id)


def post_bank_transfer(session: Session, *, from_bank_id: int, to_bank_id: int,
                       on: date, amount: float,
                       memo: str = "Bank transfer") -> JournalEntry:
    """DR Destination Bank / CR Source Bank."""
    src = session.get(BankAccount, from_bank_id)
    dst = session.get(BankAccount, to_bank_id)
    if not src or not dst:
        raise ValueError("Both bank accounts must exist.")
    return post_journal(session, on, memo, [
        JELine(account_id=dst.gl_account_id, debit=amount, memo=memo),
        JELine(account_id=src.gl_account_id, credit=amount, memo=memo),
    ], source_kind="BANK_XFER")


def reconcile(
    session: Session, bank_account_id: int, statement_balance: float,
    *, as_of: Optional[date] = None,
) -> dict:
    """Compare GL bank balance against a statement balance. Returns the diff.

    A real reconciliation would match each statement line to a JE line; this
    is the headline summary that surfaces a delta to investigate.
    """
    gl_balance = bank_balance(session, bank_account_id, as_of=as_of)
    diff = round(statement_balance - gl_balance, 2)
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "gl_balance": gl_balance,
        "statement_balance": statement_balance,
        "difference": diff,
        "reconciled": abs(diff) < 0.01,
    }
