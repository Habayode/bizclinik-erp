"""Forward-looking FP&A: trend forecast, rolling cash flow, next-year budget.

All projections are built from the company's OWN posted history — per income and
expense account, the trailing monthly run-rate and its trend are extended
forward. This is an indicative, trend-based model (not a guarantee): it assumes
recent patterns continue and, for cash flow, that new sales are collected in the
month and existing receivables/payables run off over their aging buckets. Those
assumptions are returned alongside the numbers so they can be shown to the user.

Functions are pure-ish (read-only) except `save_as_budget`, which writes the
generated next-year plan into the existing Budgets module so it drives
budget-vs-actual reporting.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import reports

_GROWTH_CAP = 0.10  # ±10% per month — keep projections sane on thin history


# ---- month helpers ---------------------------------------------------------

def _trailing_keys(end: date, count: int) -> list[tuple[int, int]]:
    """`count` (year, month) keys ending at `end`'s month, oldest first."""
    y, m = end.year, end.month
    keys: list[tuple[int, int]] = []
    for _ in range(count):
        keys.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(keys))


def _add_months(y: int, m: int, k: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + k
    return idx // 12, idx % 12 + 1


def _label(y: int, m: int) -> str:
    return f"{y}-{m:02d}"


# ---- actuals + per-account trend -------------------------------------------

def _monthly_account_actuals(session: Session, *, as_of: date, months_back: int):
    """Per income/expense account, the monthly amount (signed on its normal
    side: revenue +, expense +) over the trailing window."""
    from ..models import Account, AccountType, DocStatus, JournalEntry, JournalLine

    keys = _trailing_keys(as_of, months_back)
    start_y, start_m = keys[0]
    window_start = date(start_y, start_m, 1)

    rows = session.execute(
        select(JournalLine.debit, JournalLine.credit, JournalEntry.entry_date,
               Account.id, Account.name, Account.type)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(JournalEntry.status == DocStatus.POSTED,
               JournalEntry.entry_date >= window_start,
               JournalEntry.entry_date <= as_of,
               Account.type.in_([AccountType.INCOME, AccountType.EXPENSE]))
    ).all()

    accts: dict[int, dict] = {}
    for debit, credit, edate, aid, aname, atype in rows:
        d = accts.setdefault(aid, {"name": aname, "type": atype, "months": {}})
        key = (edate.year, edate.month)
        # Income is credit-normal; expense is debit-normal.
        amt = ((credit or 0.0) - (debit or 0.0)) if atype == AccountType.INCOME \
            else ((debit or 0.0) - (credit or 0.0))
        d["months"][key] = d["months"].get(key, 0.0) + amt
    return accts, keys


def _trend(series: list[float]) -> tuple[float, float]:
    """(base run-rate, monthly growth) from a trailing series."""
    n = len(series)
    base = sum(series) / n if n else 0.0
    half = n // 2 or 1
    fh = sum(series[:half]) / half
    sh = sum(series[half:]) / max(n - half, 1)
    if n >= 4 and fh > 1e-9 and sh > 1e-9:
        g = (sh / fh) ** (1.0 / max(half, 1)) - 1.0
    else:
        g = 0.0
    return base, max(-_GROWTH_CAP, min(_GROWTH_CAP, g))


def _account_models(session: Session, *, as_of: date, months_back: int):
    """For each active account: {id, name, kind(income|expense), base, growth}."""
    from ..models import AccountType
    accts, keys = _monthly_account_actuals(session, as_of=as_of, months_back=months_back)
    models = []
    for aid, d in accts.items():
        series = [d["months"].get(k, 0.0) for k in keys]
        if abs(sum(series)) < 1.0:
            continue  # inactive account
        base, growth = _trend(series)
        models.append({
            "id": aid, "name": d["name"],
            "kind": "income" if d["type"] == AccountType.INCOME else "expense",
            "base": base, "growth": growth,
        })
    return models, keys


# ---- the public bundle -----------------------------------------------------

def forecast_bundle(session: Session, *, as_of: Optional[date] = None,
                    horizon: int = 12, months_back: int = 12) -> dict:
    if as_of is None:
        as_of = date.today()
    models, keys = _account_models(session, as_of=as_of, months_back=months_back)

    # Trailing actuals (aggregate, from the raw ledger).
    monthly_actuals = _aggregate_actuals(session, as_of=as_of, keys=keys)

    # Aggregate P&L forecast, horizon months forward.
    pnl_forecast = []
    for t in range(1, horizon + 1):
        ny, nm = _add_months(as_of.year, as_of.month, t)
        rev = sum(max(a["base"] * (1 + a["growth"]) ** t, 0.0)
                  for a in models if a["kind"] == "income")
        cost = sum(max(a["base"] * (1 + a["growth"]) ** t, 0.0)
                   for a in models if a["kind"] == "expense")
        pnl_forecast.append({"label": _label(ny, nm),
                             "revenue": round(rev, 2), "costs": round(cost, 2),
                             "net": round(rev - cost, 2)})

    # Next-year budget (per account, 12 calendar months).
    next_year = as_of.year + 1
    budget_rows = []
    for a in models:
        for mm in range(1, 13):
            ahead = (next_year - as_of.year) * 12 + (mm - as_of.month)
            amt = a["base"] * (1 + a["growth"]) ** max(ahead, 1)
            amt = round(max(amt, 0.0), 2)
            if amt <= 0:
                continue
            budget_rows.append({"account_id": a["id"], "account_name": a["name"],
                                "kind": a["kind"], "month": mm, "amount": amt})
    annual = _budget_annual(budget_rows, next_year)
    trailing_rev = sum(r["revenue"] for r in monthly_actuals)
    annual["growth_pct"] = (round((annual["revenue"] - trailing_rev) / trailing_rev * 100, 1)
                            if trailing_rev > 0 else None)

    cash_flow = _rolling_cash_flow(session, as_of=as_of, horizon=horizon,
                                   pnl_forecast=pnl_forecast)

    return {
        "as_of": as_of.isoformat(),
        "horizon": horizon,
        "months_back": months_back,
        "monthly_actuals": monthly_actuals,
        "pnl_forecast": pnl_forecast,
        "annual": annual,
        "budget_year": next_year,
        "budget_rows": budget_rows,
        "cash_flow": cash_flow,
        "assumptions": [
            "Per-account trailing run-rate extended by its own trend "
            f"(capped at ±{int(_GROWTH_CAP * 100)}%/month).",
            "Cash flow assumes new sales are collected in-month and existing "
            "receivables/payables run off over their aging buckets.",
            "Indicative only — not a guarantee of future results.",
        ],
    }


def _aggregate_actuals(session: Session, *, as_of: date, keys) -> list[dict]:
    from ..models import AccountType
    accts, _ = _monthly_account_actuals(session, as_of=as_of, months_back=len(keys))
    out = []
    for (y, m) in keys:
        rev = sum(d["months"].get((y, m), 0.0)
                  for d in accts.values() if d["type"] == AccountType.INCOME)
        cost = sum(d["months"].get((y, m), 0.0)
                   for d in accts.values() if d["type"] == AccountType.EXPENSE)
        out.append({"label": _label(y, m), "revenue": round(rev, 2),
                    "costs": round(cost, 2), "net": round(rev - cost, 2)})
    return out


def _budget_annual(budget_rows: list[dict], year: int) -> dict:
    rev = sum(r["amount"] for r in budget_rows if r["kind"] == "income")
    cost = sum(r["amount"] for r in budget_rows if r["kind"] == "expense")
    return {"year": year, "revenue": round(rev, 2), "costs": round(cost, 2),
            "net": round(rev - cost, 2)}


def _cash_on_hand(session: Session, as_of: date) -> float:
    bs = reports.balance_sheet(session, as_of=as_of)
    total = 0.0
    for a in bs.get("assets", []):
        name = (a.get("name") or "").lower()
        if any(w in name for w in ("cash", "bank")):
            total += a.get("amount", 0.0)
    return round(total, 2)


def _rolling_cash_flow(session: Session, *, as_of: date, horizon: int,
                       pnl_forecast: list[dict]) -> dict:
    opening = _cash_on_hand(session, as_of)
    ar = reports.ar_aging(session, as_of=as_of)
    ap = reports.ap_aging(session, as_of=as_of)

    ar_soon = sum(r.get("0-30", 0) + r.get("31-60", 0) for r in ar)
    ar_late = sum(r.get("61-90", 0) + r.get("90+", 0) for r in ar)
    ap_soon = sum(r.get("0-30", 0) + r.get("31-60", 0) for r in ap)
    ap_late = sum(r.get("61-90", 0) + r.get("90+", 0) for r in ap)

    rows = []
    balance = opening
    first_negative = None
    min_balance = opening
    for t, pf in enumerate(pnl_forecast, start=1):
        inflow = pf["revenue"]
        outflow = pf["costs"]
        if t == 1:
            inflow += ar_soon
            outflow += ap_soon
        elif t == 2:
            inflow += ar_late
            outflow += ap_late
        net = round(inflow - outflow, 2)
        balance = round(balance + net, 2)
        if balance < min_balance:
            min_balance = balance
        if first_negative is None and balance < 0:
            first_negative = {"label": pf["label"], "shortfall": balance}
        rows.append({"label": pf["label"], "inflow": round(inflow, 2),
                     "outflow": round(outflow, 2), "net": net, "balance": balance})
    return {"opening": opening, "rows": rows, "min_balance": min_balance,
            "ending": balance, "first_negative": first_negative}


# ---- persist into the Budgets module ---------------------------------------

def save_as_budget(session: Session, *, as_of: Optional[date] = None,
                   months_back: int = 12, name: Optional[str] = None) -> dict:
    """Generate next year's budget and save it via the Budgets module."""
    from .. import authz
    from . import budget as budget_svc
    authz.require_perm("agents.run")
    if as_of is None:
        as_of = date.today()
    bundle = forecast_bundle(session, as_of=as_of, horizon=12, months_back=months_back)
    year = bundle["budget_year"]
    b = budget_svc.create_budget(
        session, name=name or f"FY{year} Forecast (FP&A Agent)", year=year)
    rows = [{"account_id": r["account_id"], "month": r["month"], "amount": r["amount"]}
            for r in bundle["budget_rows"]]
    n = budget_svc.bulk_set(session, b.id, rows)
    return {"budget_id": b.id, "name": b.name, "year": year, "lines": n,
            "revenue": bundle["annual"]["revenue"], "net": bundle["annual"]["net"]}
