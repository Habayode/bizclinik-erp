"""Financial reports: P&L, Balance Sheet, Cash Flow, AR/AP aging.

These all read directly from the posted general ledger so they are always
consistent with the underlying journal entries. Balance Sheet uses the
standard accounting equation Assets = Liabilities + Equity (where Equity
includes period earnings).
"""
from __future__ import annotations
from ..money import msum

from collections import defaultdict
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    AccountType,
    Bill,
    Customer,
    DocStatus,
    JournalEntry,
    JournalLine,
    SalesInvoice,
    Supplier,
)
from ..models.master import NORMAL_BALANCE
from .ledger import account_balance


# ---- P&L --------------------------------------------------------------------


def profit_and_loss(
    session: Session, *, period_start: date, period_end: date,
) -> dict:
    """Income statement for a period.

    Revenue (INCOME accounts), less Cost of Sales (EXPENSE in 5xxx range),
    gives Gross Profit. Less remaining EXPENSE = Net Profit.
    """
    accts = session.execute(
        select(Account).where(
            Account.type.in_([AccountType.INCOME, AccountType.EXPENSE]),
            Account.is_postable == True,  # noqa: E712
        ).order_by(Account.code)
    ).scalars().all()

    revenue, other_income, direct_costs, opex = [], [], [], []
    for a in accts:
        bal = account_balance(session, a.id,
                              period_start=period_start, as_of=period_end)
        if bal == 0:
            continue
        row = {"code": a.code, "name": a.name, "amount": bal}
        if a.type == AccountType.INCOME:
            # Operating revenue: 41xx (sales/service/food/beverage) and 44xx
            # (school fees: tuition, exam, uniform, transport, levies, …). The
            # rest of INCOME — 42xx interest/commission, 43xx FX, 49xx disposal
            # gains — is non-operating "other income".
            if a.code.startswith(("41", "44")):
                revenue.append(row)
            else:
                other_income.append(row)
        else:  # EXPENSE
            if a.code.startswith("5"):
                direct_costs.append(row)
            else:
                opex.append(row)

    total_revenue = sum(r["amount"] for r in revenue)
    total_other = sum(r["amount"] for r in other_income)
    total_direct = sum(r["amount"] for r in direct_costs)
    total_opex = sum(r["amount"] for r in opex)
    gross_profit = total_revenue - total_direct
    operating_profit = gross_profit - total_opex
    net_profit = operating_profit + total_other

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "revenue": revenue, "total_revenue": round(total_revenue, 2),
        "other_income": other_income, "total_other_income": round(total_other, 2),
        "direct_costs": direct_costs, "total_direct_costs": round(total_direct, 2),
        "operating_expenses": opex, "total_operating_expenses": round(total_opex, 2),
        "gross_profit": round(gross_profit, 2),
        "operating_profit": round(operating_profit, 2),
        "net_profit": round(net_profit, 2),
    }


# ---- Balance Sheet ----------------------------------------------------------


def balance_sheet(session: Session, *, as_of: date,
                  fiscal_year_start: Optional[date] = None) -> dict:
    """Snapshot of A = L + E at a given date.

    There are no year-end closing entries — income/expense balances accrue
    across years — so equity must absorb ALL net income earned up to as_of, not
    just the current year's. We split it for presentation: "Retained Earnings"
    (everything before `fiscal_year_start`) plus "Current Year Earnings"
    (fiscal_year_start through as_of). Their sum is the all-time net income,
    which is what keeps A = L + E. (Default fiscal_year_start: 1 Jan of the
    as_of year.)
    """
    fy_start = fiscal_year_start or date(as_of.year, 1, 1)
    accts = session.execute(
        select(Account).where(Account.is_postable == True).order_by(Account.code)  # noqa: E712
    ).scalars().all()

    assets, liabilities, equity = [], [], []
    for a in accts:
        if a.type not in (AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY):
            continue
        bal = account_balance(session, a.id, as_of=as_of)
        if bal == 0:
            continue
        row = {"code": a.code, "name": a.name, "amount": bal}
        if a.type == AccountType.ASSET:
            assets.append(row)
        elif a.type == AccountType.LIABILITY:
            liabilities.append(row)
        else:
            equity.append(row)

    # Equity must absorb all net income to date (no year-end close zeroes the
    # P&L). Prior-year accumulated earnings (everything before fy_start) become
    # Retained Earnings; the rest is Current Year Earnings.
    prior_end = date.fromordinal(fy_start.toordinal() - 1)
    retained = profit_and_loss(session, period_start=date(1900, 1, 1),
                               period_end=prior_end)["net_profit"]
    ytd_earnings = profit_and_loss(session, period_start=fy_start,
                                   period_end=as_of)["net_profit"]
    if retained != 0:
        equity.append({"code": "3200", "name": "Retained Earnings (prior years)",
                        "amount": round(retained, 2)})
    if ytd_earnings != 0:
        equity.append({"code": "3300", "name": "Current Year Earnings",
                        "amount": round(ytd_earnings, 2)})

    total_assets = msum(r["amount"] for r in assets)
    total_liab = msum(r["amount"] for r in liabilities)
    total_equity = msum(r["amount"] for r in equity)
    diff = round(total_assets - (total_liab + total_equity), 2)

    return {
        "as_of": as_of.isoformat(),
        "fiscal_year_start": fy_start.isoformat(),
        "assets": assets, "total_assets": total_assets,
        "liabilities": liabilities, "total_liabilities": total_liab,
        "equity": equity, "total_equity": total_equity,
        "balanced": abs(diff) < 0.01,
        "imbalance": diff,
        "ytd_earnings": ytd_earnings,
    }


# ---- Cash Flow (indirect) ---------------------------------------------------


def cash_flow(session: Session, *, period_start: date, period_end: date) -> dict:
    """Indirect-method cash flow.

    Operating cash = Net Profit
        + Depreciation
        + Decrease in AR + Decrease in Inventory + Decrease in Input VAT
        + Increase in AP + Increase in Output VAT
    Investing cash = - (increase in Fixed Assets)
    Financing cash = + Share Capital changes
    Net change in cash should match the bank/cash account delta.
    """
    pnl = profit_and_loss(session, period_start=period_start, period_end=period_end)
    net_profit = pnl["net_profit"]

    def _delta(code: str) -> float:
        opening = account_balance(session, _acct_id(session, code),
                                  as_of=date.fromordinal(period_start.toordinal() - 1))
        closing = account_balance(session, _acct_id(session, code), as_of=period_end)
        return round(closing - opening, 2)

    ar_delta = _delta("1130")        # asset — increase reduces cash
    inv_delta = _delta("1140")
    ap_delta = _delta("2110")        # liability — increase ADDS cash
    out_vat_delta = _delta("2120")
    in_vat_delta = _delta("1150")
    depreciation = _delta("1290")    # accumulated dep (credit balance increase)
    fa_equip_delta = _delta("1210")
    fa_furn_delta = _delta("1220")
    share_cap_delta = _delta("3100")

    operating = round(
        net_profit
        + depreciation
        - ar_delta
        - inv_delta
        - in_vat_delta
        + ap_delta
        + out_vat_delta,
        2,
    )
    investing = round(-(fa_equip_delta + fa_furn_delta), 2)
    financing = round(share_cap_delta, 2)
    net_cash = round(operating + investing + financing, 2)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "operating_activities": {
            "net_profit": net_profit,
            "depreciation": depreciation,
            "change_in_ar": -ar_delta,
            "change_in_inventory": -inv_delta,
            "change_in_input_vat": -in_vat_delta,
            "change_in_ap": ap_delta,
            "change_in_output_vat": out_vat_delta,
            "total": operating,
        },
        "investing_activities": {
            "change_in_equipment": -fa_equip_delta,
            "change_in_furniture": -fa_furn_delta,
            "total": investing,
        },
        "financing_activities": {
            "change_in_share_capital": share_cap_delta,
            "total": financing,
        },
        "net_change_in_cash": net_cash,
    }


def _acct_id(session: Session, code: str) -> int:
    a = session.execute(select(Account).where(Account.code == code)).scalar_one_or_none()
    return a.id if a else 0


# ---- Aging ------------------------------------------------------------------


_BUCKETS = [(0, 30), (31, 60), (61, 90), (91, 99_999)]
_BUCKET_LABELS = ["0-30", "31-60", "61-90", "90+"]


def _bucket(days: int) -> str:
    for (lo, hi), lbl in zip(_BUCKETS, _BUCKET_LABELS):
        if lo <= days <= hi:
            return lbl
    return "90+"


def ar_aging(session: Session, *, as_of: date) -> list[dict]:
    """Unpaid customer invoices grouped by customer and aging bucket."""
    invs = session.execute(
        select(SalesInvoice).where(
            SalesInvoice.status.in_([DocStatus.POSTED, DocStatus.PARTIAL]),
            SalesInvoice.invoice_date <= as_of,
        )
    ).scalars().all()
    by_cust: dict[int, dict] = {}
    for inv in invs:
        outstanding = round(inv.grand_total - inv.amount_paid, 2)
        if outstanding <= 0:
            continue
        due = inv.due_date or inv.invoice_date
        days = (as_of - due).days
        b = _bucket(days)
        slot = by_cust.setdefault(inv.customer_id, {
            "customer_id": inv.customer_id,
            "customer_name": inv.customer.name if inv.customer else "",
            "total": 0.0,
            **{lbl: 0.0 for lbl in _BUCKET_LABELS},
        })
        slot[b] += outstanding
        slot["total"] += outstanding
    return [
        {**v,
         "total": round(v["total"], 2),
         **{lbl: round(v[lbl], 2) for lbl in _BUCKET_LABELS}}
        for v in by_cust.values()
    ]


def ap_aging(session: Session, *, as_of: date) -> list[dict]:
    bills = session.execute(
        select(Bill).where(
            Bill.status.in_([DocStatus.POSTED, DocStatus.PARTIAL]),
            Bill.bill_date <= as_of,
        )
    ).scalars().all()
    by_sup: dict[int, dict] = {}
    for b in bills:
        outstanding = round(b.grand_total - b.amount_paid, 2)
        if outstanding <= 0:
            continue
        due = b.due_date or b.bill_date
        days = (as_of - due).days
        bkt = _bucket(days)
        slot = by_sup.setdefault(b.supplier_id, {
            "supplier_id": b.supplier_id,
            "supplier_name": b.supplier.name if b.supplier else "",
            "total": 0.0,
            **{lbl: 0.0 for lbl in _BUCKET_LABELS},
        })
        slot[bkt] += outstanding
        slot["total"] += outstanding
    return [
        {**v,
         "total": round(v["total"], 2),
         **{lbl: round(v[lbl], 2) for lbl in _BUCKET_LABELS}}
        for v in by_sup.values()
    ]
