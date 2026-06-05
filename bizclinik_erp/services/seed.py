"""Seed a standard Nigerian SME chart of accounts and default tax codes.

Idempotent — calling seed_defaults() repeatedly inserts only what's missing.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Account, AccountType, BankAccount, TaxCode, Warehouse


# (code, name, type, parent_code, postable)
STANDARD_COA: list[tuple[str, str, AccountType, str | None, bool]] = [
    # Assets
    ("1000", "Assets", AccountType.ASSET, None, False),
    ("1100", "Current Assets", AccountType.ASSET, "1000", False),
    ("1110", "Cash on Hand", AccountType.ASSET, "1100", True),
    ("1120", "Bank — Operating", AccountType.ASSET, "1100", True),
    ("1130", "Accounts Receivable", AccountType.ASSET, "1100", True),
    ("1140", "Inventory — Stock", AccountType.ASSET, "1100", True),
    ("1150", "Input VAT", AccountType.ASSET, "1100", True),
    ("1160", "Withholding Tax Receivable", AccountType.ASSET, "1100", True),
    ("1170", "Prepaid Expenses", AccountType.ASSET, "1100", True),
    ("1200", "Fixed Assets", AccountType.ASSET, "1000", False),
    ("1210", "Equipment", AccountType.ASSET, "1200", True),
    ("1220", "Furniture & Fittings", AccountType.ASSET, "1200", True),
    ("1290", "Accumulated Depreciation", AccountType.ASSET, "1200", True),
    # Liabilities
    ("2000", "Liabilities", AccountType.LIABILITY, None, False),
    ("2100", "Current Liabilities", AccountType.LIABILITY, "2000", False),
    ("2110", "Accounts Payable", AccountType.LIABILITY, "2100", True),
    ("2120", "Output VAT", AccountType.LIABILITY, "2100", True),
    ("2130", "PAYE Payable", AccountType.LIABILITY, "2100", True),
    ("2140", "Pension Payable", AccountType.LIABILITY, "2100", True),
    ("2150", "Withholding Tax Payable", AccountType.LIABILITY, "2100", True),
    ("2160", "Accrued Expenses", AccountType.LIABILITY, "2100", True),
    # Equity
    ("3000", "Equity", AccountType.EQUITY, None, False),
    ("3100", "Share Capital", AccountType.EQUITY, "3000", True),
    ("3200", "Retained Earnings", AccountType.EQUITY, "3000", True),
    ("3300", "Current Year Earnings", AccountType.EQUITY, "3000", True),
    # Income
    ("4000", "Income", AccountType.INCOME, None, False),
    ("4100", "Sales", AccountType.INCOME, "4000", True),
    ("4200", "Other Income", AccountType.INCOME, "4000", True),
    ("4210", "Interest Income", AccountType.INCOME, "4000", True),
    ("4220", "Commission Received", AccountType.INCOME, "4000", True),
    ("4230", "Discount Received", AccountType.INCOME, "4000", True),
    # Expenses
    ("5000", "Cost of Sales", AccountType.EXPENSE, None, False),
    ("5100", "Cost of Goods Sold", AccountType.EXPENSE, "5000", True),
    ("6000", "Operating Expenses", AccountType.EXPENSE, None, False),
    ("6100", "Salaries & Wages", AccountType.EXPENSE, "6000", True),
    ("6110", "Pension Employer Contribution", AccountType.EXPENSE, "6000", True),
    ("6200", "Rent & Utilities", AccountType.EXPENSE, "6000", True),
    ("6300", "Diesel & Fuel", AccountType.EXPENSE, "6000", True),
    ("6400", "Marketing & Branding", AccountType.EXPENSE, "6000", True),
    ("6500", "Bank Charges", AccountType.EXPENSE, "6000", True),
    ("6600", "Depreciation Expense", AccountType.EXPENSE, "6000", True),
    ("6900", "Other Operating Expenses", AccountType.EXPENSE, "6000", True),
]


def _get_or_create_account(
    session: Session, code: str, name: str, type_: AccountType,
    parent_code: str | None, postable: bool,
) -> Account:
    existing = session.execute(
        select(Account).where(Account.code == code)
    ).scalar_one_or_none()
    if existing:
        return existing
    parent = None
    if parent_code:
        parent = session.execute(
            select(Account).where(Account.code == parent_code)
        ).scalar_one_or_none()
    acct = Account(
        code=code, name=name, type=type_,
        parent_id=parent.id if parent else None,
        is_postable=postable,
    )
    session.add(acct)
    session.flush()
    return acct


def seed_chart_of_accounts(session: Session) -> None:
    for row in STANDARD_COA:
        _get_or_create_account(session, *row)


def seed_tax_codes(session: Session) -> None:
    s = get_settings()
    out_acct = session.execute(
        select(Account).where(Account.code == "2120")
    ).scalar_one()
    in_acct = session.execute(
        select(Account).where(Account.code == "1150")
    ).scalar_one()

    wht_payable = session.execute(
        select(Account).where(Account.code == "2150")
    ).scalar_one()
    wht_receivable = session.execute(
        select(Account).where(Account.code == "1160")
    ).scalar_one()

    presets = [
        ("VAT", "Standard VAT", s.default_vat_rate, out_acct.id, in_acct.id),
        ("VAT0", "Zero-rated VAT", 0.0, out_acct.id, in_acct.id),
        ("EXEMPT", "VAT Exempt", 0.0, None, None),
        ("WHT5", "Withholding Tax 5%", s.default_wht_rate,
         wht_payable.id, wht_receivable.id),
    ]
    for code, name, rate, out_id, in_id in presets:
        existing = session.execute(
            select(TaxCode).where(TaxCode.code == code)
        ).scalar_one_or_none()
        if existing:
            continue
        session.add(TaxCode(code=code, name=name, rate=rate,
                            output_account_id=out_id, input_account_id=in_id))


def seed_warehouses_and_bank(session: Session) -> None:
    if not session.execute(select(Warehouse).where(Warehouse.code == "MAIN")).scalar_one_or_none():
        session.add(Warehouse(code="MAIN", name="Main Warehouse"))
    bank_acct = session.execute(
        select(Account).where(Account.code == "1120")
    ).scalar_one()
    if not session.execute(select(BankAccount).where(BankAccount.code == "BANK1")).scalar_one_or_none():
        session.add(BankAccount(
            code="BANK1", name="Primary Bank Account",
            bank="(set in Settings)", account_number="",
            gl_account_id=bank_acct.id,
        ))
    cash_acct = session.execute(
        select(Account).where(Account.code == "1110")
    ).scalar_one()
    if not session.execute(select(BankAccount).where(BankAccount.code == "CASH")).scalar_one_or_none():
        session.add(BankAccount(
            code="CASH", name="Cash on Hand", bank="(petty cash)",
            gl_account_id=cash_acct.id,
        ))


def seed_disposal_account(session: Session) -> None:
    """Seed the Gain/Loss on Asset Disposal income account (code 4900).

    Used by services.assets.dispose_asset() as the balancer when an asset is
    retired. Sits under the existing 4000 Income parent so the P&L picks it up.
    """
    _get_or_create_account(
        session, "4900", "Gain/Loss on Asset Disposal",
        AccountType.INCOME, "4000", True,
    )


def seed_defaults(session: Session) -> None:
    seed_chart_of_accounts(session)
    seed_tax_codes(session)
    seed_disposal_account(session)
    seed_warehouses_and_bank(session)
