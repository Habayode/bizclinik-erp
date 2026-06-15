"""Fixed Assets service.

Three responsibilities:
  * Register new capital items (add_asset).
  * Run monthly depreciation catch-up across all active assets
    (run_depreciation), posting one JE per asset per month.
  * Handle disposal (dispose_asset) — remove asset + accumulated depreciation
    from the books, recognise gain or loss on the difference vs proceeds.

All GL impact flows through services.ledger.post_journal so the trial balance
invariant (sum DR == sum CR) is preserved.
"""
from __future__ import annotations

import calendar
import math
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    AssetStatus,
    BankAccount,
    DepreciationMethod,
    FixedAsset,
    JournalEntry,
)
from .ledger import JELine, post_journal


# ---- date helpers ----------------------------------------------------------


def _end_of_month(d: date) -> date:
    last_day = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def _add_one_month(d: date) -> date:
    """Return the first day of the month following d."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


# ---- registration ----------------------------------------------------------


def add_asset(
    session: Session,
    *,
    code: str,
    name: str,
    category: str,
    acquired_date: date,
    cost: float,
    useful_life_months: int,
    gl_asset_account_id: int,
    gl_accum_dep_account_id: int,
    gl_dep_expense_account_id: int,
    salvage_value: float = 0.0,
) -> FixedAsset:
    """Insert a new FixedAsset. Does NOT post the acquisition JE — that is
    captured separately when the supplier bill or cash payment is recorded."""
    if cost <= 0:
        raise ValueError("Asset cost must be positive.")
    if useful_life_months <= 0:
        raise ValueError("Useful life (months) must be positive.")
    if salvage_value < 0 or salvage_value >= cost:
        raise ValueError("Salvage value must be in [0, cost).")

    asset = FixedAsset(
        code=code,
        name=name,
        category=category,
        acquired_date=acquired_date,
        cost=cost,
        salvage_value=salvage_value,
        useful_life_months=useful_life_months,
        depreciation_method=DepreciationMethod.STRAIGHT_LINE,
        gl_asset_account_id=gl_asset_account_id,
        gl_accum_dep_account_id=gl_accum_dep_account_id,
        gl_dep_expense_account_id=gl_dep_expense_account_id,
        status=AssetStatus.ACTIVE,
        accumulated_depreciation=0.0,
    )
    session.add(asset)
    session.flush()
    return asset


# ---- depreciation ----------------------------------------------------------


def monthly_depreciation_amount(asset: FixedAsset) -> float:
    """Per-month charge under straight-line: (cost - salvage) / life_months."""
    if asset.depreciation_method != DepreciationMethod.STRAIGHT_LINE:
        raise NotImplementedError(f"Unsupported method: {asset.depreciation_method}")
    if asset.useful_life_months <= 0:
        return 0.0
    return round((asset.cost - asset.salvage_value) / asset.useful_life_months, 2)


def _months_to_post(asset: FixedAsset, as_of: date) -> list[date]:
    """List of month-end dates we should post depreciation on, given the
    current state of the asset and the as_of cutoff. We post for every full
    calendar month whose end date is <= the end of the month preceding as_of.
    """
    # Starting point: the first calendar month we have NOT yet booked.
    if asset.last_depreciation_date is not None:
        # last_depreciation_date is always a month-end stamp — start the
        # month after it.
        start_month_first = _add_one_month(asset.last_depreciation_date)
    else:
        # First charge is the month of acquisition.
        start_month_first = _first_of_month(asset.acquired_date)

    # Cutoff: we only post months whose end is strictly before the start of
    # the as_of month — i.e. complete months that precede as_of.
    cutoff_month_first = _first_of_month(as_of)

    months: list[date] = []
    cursor = start_month_first
    while cursor < cutoff_month_first:
        months.append(_end_of_month(cursor))
        cursor = _add_one_month(cursor)

    # Cap the list by the VALUE still to depreciate, not a rounded month count.
    # Deriving the bound from int(round(accumulated / monthly)) truncates one
    # month too early when the accumulated depreciation isn't an exact multiple
    # of the monthly charge (e.g. an NBV-derived figure carried in on import),
    # which would strand value above salvage forever. ceil() keeps the final
    # partial month; run_depreciation's per-charge cap then sizes it exactly.
    monthly = monthly_depreciation_amount(asset)
    if monthly <= 0:
        return []
    remaining_value = round(
        (asset.cost - asset.salvage_value) - asset.accumulated_depreciation, 2)
    if remaining_value <= 0:
        return []
    remaining_months = math.ceil(remaining_value / monthly - 1e-9)
    if remaining_months < len(months):
        months = months[:remaining_months]
    return months


def run_depreciation(session: Session, *, as_of: date) -> list[JournalEntry]:
    """Catch up depreciation for every ACTIVE asset up to the start of the
    as_of month. Posts one JE per asset per missed month. Returns the list of
    JEs created (possibly empty).
    """
    assets = session.execute(
        select(FixedAsset).where(FixedAsset.status == AssetStatus.ACTIVE)
    ).scalars().all()

    created: list[JournalEntry] = []
    for asset in assets:
        monthly = monthly_depreciation_amount(asset)
        if monthly <= 0:
            continue
        for month_end in _months_to_post(asset, as_of):
            # Cap last charge so we never over-depreciate past (cost - salvage).
            depreciable_base = asset.cost - asset.salvage_value
            remaining_to_depreciate = round(
                depreciable_base - asset.accumulated_depreciation, 2
            )
            charge = min(monthly, remaining_to_depreciate)
            if charge <= 0:
                break
            je = post_journal(
                session,
                month_end,
                f"Depreciation — {asset.code} {asset.name} ({month_end:%Y-%m})",
                [
                    JELine(
                        account_id=asset.gl_dep_expense_account_id,
                        debit=charge,
                        memo=f"Depreciation {asset.code}",
                    ),
                    JELine(
                        account_id=asset.gl_accum_dep_account_id,
                        credit=charge,
                        memo=f"Accum dep {asset.code}",
                    ),
                ],
                source_kind="DEPRECIATION",
                source_id=asset.id,
            )
            asset.accumulated_depreciation = round(
                asset.accumulated_depreciation + charge, 2
            )
            asset.last_depreciation_date = month_end
            created.append(je)
    session.flush()
    return created


# ---- disposal --------------------------------------------------------------


_DISPOSAL_GAINLOSS_CODE = "4900"


def _disposal_account_id(session: Session) -> int:
    acct = session.execute(
        select(Account).where(Account.code == _DISPOSAL_GAINLOSS_CODE)
    ).scalar_one_or_none()
    if acct is None:
        raise RuntimeError(
            f"Gain/Loss on Asset Disposal account ({_DISPOSAL_GAINLOSS_CODE}) "
            "not seeded. Run seed_defaults()."
        )
    return acct.id


def dispose_asset(
    session: Session,
    asset_id: int,
    *,
    on: date,
    proceeds: float,
    bank_account_id: int,
) -> JournalEntry:
    """Retire an asset. Posts a balanced JE:

        DR Bank (proceeds)
        DR Accumulated Depreciation (everything booked to date)
        CR Asset (original cost)
        +/- Gain/Loss balancer

    NBV = cost - accumulated_depreciation. Gain when proceeds > NBV, loss
    when proceeds < NBV. The balancer hits account 4900.
    """
    asset = session.get(FixedAsset, asset_id)
    if asset is None:
        raise ValueError(f"FixedAsset id={asset_id} not found.")
    if asset.status == AssetStatus.DISPOSED:
        raise ValueError(f"Asset {asset.code} is already disposed.")
    if proceeds < 0:
        raise ValueError("Proceeds must be non-negative.")

    bank = session.get(BankAccount, bank_account_id)
    if bank is None:
        raise ValueError(f"BankAccount id={bank_account_id} not found.")

    gainloss_acct_id = _disposal_account_id(session)
    cost = round(asset.cost, 2)
    accum = round(asset.accumulated_depreciation, 2)
    nbv = round(cost - accum, 2)
    gain_or_loss = round(proceeds - nbv, 2)  # +ve = gain (credit), -ve = loss (debit)

    lines: list[JELine] = []
    if proceeds > 0:
        lines.append(JELine(
            account_id=bank.gl_account_id,
            debit=proceeds,
            memo=f"Disposal proceeds — {asset.code}",
        ))
    if accum > 0:
        lines.append(JELine(
            account_id=asset.gl_accum_dep_account_id,
            debit=accum,
            memo=f"Clear accum dep — {asset.code}",
        ))
    lines.append(JELine(
        account_id=asset.gl_asset_account_id,
        credit=cost,
        memo=f"Retire asset — {asset.code}",
    ))
    if gain_or_loss > 0:
        # Gain — credit income.
        lines.append(JELine(
            account_id=gainloss_acct_id,
            credit=gain_or_loss,
            memo=f"Gain on disposal — {asset.code}",
        ))
    elif gain_or_loss < 0:
        # Loss — debit (since 4900 sits under Income, this reduces net income).
        lines.append(JELine(
            account_id=gainloss_acct_id,
            debit=-gain_or_loss,
            memo=f"Loss on disposal — {asset.code}",
        ))

    je = post_journal(
        session,
        on,
        f"Asset disposal — {asset.code} {asset.name}",
        lines,
        source_kind="ASSET_DISPOSAL",
        source_id=asset.id,
    )
    asset.status = AssetStatus.DISPOSED
    asset.disposed_date = on
    asset.disposal_proceeds = proceeds
    asset.is_active = False
    session.flush()
    return je


# ---- register / reporting --------------------------------------------------


def asset_register(session: Session, *, as_of: date) -> list[dict]:
    """List every asset with cost, accumulated depreciation, NBV, status.

    Filtered to assets acquired on or before as_of. Disposed assets after the
    as_of date are still shown as ACTIVE (point-in-time view).
    """
    assets = session.execute(
        select(FixedAsset).where(FixedAsset.acquired_date <= as_of)
        .order_by(FixedAsset.code)
    ).scalars().all()
    rows: list[dict] = []
    for a in assets:
        status_at = a.status.value
        if a.disposed_date and a.disposed_date > as_of:
            status_at = AssetStatus.ACTIVE.value
        cost = round(a.cost, 2)
        accum = round(a.accumulated_depreciation, 2)
        nbv = round(cost - accum, 2)
        rows.append({
            "id": a.id,
            "code": a.code,
            "name": a.name,
            "category": a.category,
            "acquired_date": a.acquired_date,
            "cost": cost,
            "accumulated_depreciation": accum,
            "nbv": nbv,
            "status": status_at,
            "last_depreciation_date": a.last_depreciation_date,
        })
    return rows
