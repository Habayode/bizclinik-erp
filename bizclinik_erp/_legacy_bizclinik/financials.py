"""Financial statements computed from first principles.

Aggregates Customer / Supplier / Operating module entries against the Chart
of Accounts so totals reflect the actual transaction ledger — not whatever
cached value the user last left in the P&L / Balance Sheet sheets.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from .workbook import BizClinikWorkbook


# ---- helpers ---------------------------------------------------------------


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _txn_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def _in_range(d, start: Optional[date], end: Optional[date]) -> bool:
    if d is None:
        # Entries with no date are included only when no filter is set.
        return start is None and end is None
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


# ---- data shapes -----------------------------------------------------------


@dataclass
class LineItem:
    account: str
    category: Optional[str]
    amount: float = 0.0


@dataclass
class PnLReport:
    period_start: Optional[date]
    period_end: Optional[date]
    revenue: list[LineItem] = field(default_factory=list)
    other_income: list[LineItem] = field(default_factory=list)
    direct_costs: list[LineItem] = field(default_factory=list)
    operating_expenses: list[LineItem] = field(default_factory=list)

    @property
    def total_revenue(self) -> float:
        return sum(li.amount for li in self.revenue)

    @property
    def total_other_income(self) -> float:
        return sum(li.amount for li in self.other_income)

    @property
    def total_direct_costs(self) -> float:
        return sum(li.amount for li in self.direct_costs)

    @property
    def gross_profit(self) -> float:
        return self.total_revenue - self.total_direct_costs

    @property
    def total_operating_expenses(self) -> float:
        return sum(li.amount for li in self.operating_expenses)

    @property
    def operating_profit(self) -> float:
        return self.gross_profit - self.total_operating_expenses

    @property
    def net_profit(self) -> float:
        return self.operating_profit + self.total_other_income

    def to_dict(self) -> dict:
        return {
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "revenue": [li.__dict__ for li in self.revenue],
            "other_income": [li.__dict__ for li in self.other_income],
            "direct_costs": [li.__dict__ for li in self.direct_costs],
            "operating_expenses": [li.__dict__ for li in self.operating_expenses],
            "totals": {
                "revenue": self.total_revenue,
                "other_income": self.total_other_income,
                "direct_costs": self.total_direct_costs,
                "gross_profit": self.gross_profit,
                "operating_expenses": self.total_operating_expenses,
                "operating_profit": self.operating_profit,
                "net_profit": self.net_profit,
            },
        }


@dataclass
class BalanceSheetReport:
    as_of: Optional[date]
    inventory_at_cost: float = 0.0
    inventory_lines: list[dict] = field(default_factory=list)
    vat_receivable: float = 0.0   # input VAT (paid to suppliers)
    vat_payable: float = 0.0      # output VAT (collected from customers)
    retained_earnings: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def vat_net_payable(self) -> float:
        return self.vat_payable - self.vat_receivable

    @property
    def total_derivable_assets(self) -> float:
        return self.inventory_at_cost + max(0.0, -self.vat_net_payable)

    @property
    def total_derivable_liabilities(self) -> float:
        return max(0.0, self.vat_net_payable)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "assets": {
                "inventory_at_cost": self.inventory_at_cost,
                "vat_receivable_if_net": max(0.0, -self.vat_net_payable),
                "total_derivable_assets": self.total_derivable_assets,
            },
            "liabilities": {
                "vat_payable_if_net": max(0.0, self.vat_net_payable),
                "total_derivable_liabilities": self.total_derivable_liabilities,
            },
            "equity": {
                "retained_earnings": self.retained_earnings,
            },
            "inventory_lines": self.inventory_lines,
            "vat": {
                "output_vat_on_sales": self.vat_payable,
                "input_vat_on_purchases": self.vat_receivable,
                "net_payable": self.vat_net_payable,
            },
            "notes": self.notes,
        }


# ---- computations ----------------------------------------------------------


# Categories considered for each P&L section. Pulled from Chart of Accounts
# 'Category of Accounts' column in the source workbook.
_REVENUE_CATEGORIES = {"income", "sales", "revenue"}
_OTHER_INCOME_CATEGORIES = {"other income"}
_DIRECT_COST_CATEGORIES = {"direct cost", "cost of sales", "cogs"}
_OPEX_CATEGORIES = {"operating expenses", "operating expense", "overhead", "admin"}
# Supplier entries posted to these account categories are treated as
# inventory purchases (capitalised on the balance sheet), not as expensed
# direct costs. Direct cost comes from cost-of-sale based on units sold.
_INVENTORY_CATEGORIES = {"current asset", "inventory", "stock", "stocks"}


def _category_lookup(wb: BizClinikWorkbook) -> dict[str, str]:
    """Return {account_name.lower(): category.lower()} from Chart of Accounts."""
    out: dict[str, str] = {}
    for acct in wb.chart_of_accounts():
        if acct.name and acct.category:
            out[acct.name.strip().lower()] = acct.category.strip().lower()
    return out


def _classify(category: Optional[str], default_bucket: str) -> str:
    if not category:
        return default_bucket
    c = category.strip().lower()
    if c in _REVENUE_CATEGORIES:
        return "revenue"
    if c in _OTHER_INCOME_CATEGORIES:
        return "other_income"
    if c in _DIRECT_COST_CATEGORIES:
        return "direct_costs"
    if c in _OPEX_CATEGORIES:
        return "operating_expenses"
    return default_bucket


def _is_inventory_account(category: Optional[str]) -> bool:
    if not category:
        return False
    return category.strip().lower() in _INVENTORY_CATEGORIES


def _avg_unit_cost(wb: BizClinikWorkbook,
                   as_of: Optional[date] = None) -> dict[str, float]:
    """Weighted-average purchase cost per product code (from supplier rows
    posted to an inventory account, up to `as_of` if given)."""
    cat = _category_lookup(wb)
    qty: dict[str, float] = defaultdict(float)
    val: dict[str, float] = defaultdict(float)
    for e in wb.supplier_entries():
        d = _txn_date(e.date)
        if as_of and d and d > as_of:
            continue
        name = (e.account_name or "").strip().lower()
        # Only treat the row as a stock purchase if its account is an
        # inventory category in the COA.
        if not _is_inventory_account(cat.get(name)):
            continue
        code = (e.code or "").strip()
        if not code:
            continue
        q = _num(e.qty_in)
        line_val = _num(e.rate) * q if e.rate is not None else _num(e.total)
        qty[code] += q
        val[code] += line_val
    return {c: (val[c] / qty[c]) if qty[c] else 0.0 for c in qty}


def profit_and_loss(wb: BizClinikWorkbook,
                    period_start: Optional[date] = None,
                    period_end: Optional[date] = None,
                    *, use_after_vat: bool = False) -> PnLReport:
    """Build a P&L for the given period from raw module entries.

    Accounting treatment:
      - Customer entries → revenue (or other income per Chart of Accounts).
      - Supplier entries:
          - account in an inventory category (e.g. 'Stocks' → 'Current Asset')
            → capitalised as inventory, NOT expensed here.
          - otherwise → direct cost or opex per the COA category.
      - Direct cost of sales = qty_out (from inventory module + customer
        entries, within period) × weighted-average unit cost.
      - Operating entries → opex.

    `use_after_vat=True` uses the 'Total After VAT' column instead of 'Total'.
    """
    cat = _category_lookup(wb)
    report = PnLReport(period_start=period_start, period_end=period_end)

    rev_acc: dict[str, float] = defaultdict(float)
    other_acc: dict[str, float] = defaultdict(float)
    dc_acc: dict[str, float] = defaultdict(float)
    op_acc: dict[str, float] = defaultdict(float)

    def _amount(e):
        if use_after_vat:
            return _num(getattr(e, "total_after_vat", None)) or _num(e.total)
        return _num(e.total)

    # Customer entries → revenue (or other_income if the chart says so).
    # Track customer-side qty_out per product for the COGS calc below.
    customer_qty: dict[str, float] = defaultdict(float)
    for e in wb.customer_entries():
        if not _in_range(_txn_date(e.date), period_start, period_end):
            continue
        name = (e.account_name or "Sales").strip()
        bucket = _classify(cat.get(name.lower()), default_bucket="revenue")
        amt = _amount(e)
        if bucket == "other_income":
            other_acc[name] += amt
        else:
            rev_acc[name] += amt
        if e.code:
            customer_qty[e.code.strip()] += _num(e.qty_out)

    # Supplier entries → either inventory (capitalised, not on P&L) or expense
    for e in wb.supplier_entries():
        if not _in_range(_txn_date(e.date), period_start, period_end):
            continue
        name = (e.account_name or "Cost of Sale").strip()
        category = cat.get(name.lower())
        if _is_inventory_account(category):
            # Inventory purchase — not a P&L expense in the period purchased.
            continue
        bucket = _classify(category, default_bucket="direct_costs")
        amt = _amount(e)
        if bucket == "operating_expenses":
            op_acc[name] += amt
        else:
            dc_acc[name] += amt

    # COGS — units sold × weighted-average unit cost.
    # The Inventory Module is the authoritative stock ledger; the Customer
    # Module is a revenue ledger. Use inventory qty_out as truth; fall back
    # to customer qty_out only for products that have no inventory rows
    # (otherwise we'd double-count when both modules logged the same sale).
    avg_cost = _avg_unit_cost(wb, as_of=period_end)
    movement_qty: dict[str, float] = defaultdict(float)
    codes_in_inventory: set[str] = set()
    for m in wb.inventory_movements():
        if not m.code:
            continue
        # Movements are undated in the BizClinik template — count them only
        # when no period filter is applied.
        if period_start or period_end:
            continue
        code = m.code.strip()
        codes_in_inventory.add(code)
        movement_qty[code] += (m.qty_out or 0)

    realised_qty: dict[str, float] = {}
    for code in set(customer_qty) | set(movement_qty):
        if code in codes_in_inventory:
            realised_qty[code] = movement_qty.get(code, 0.0)
        else:
            realised_qty[code] = customer_qty.get(code, 0.0)

    cogs_total = sum(q * avg_cost.get(c, 0.0) for c, q in realised_qty.items())
    if cogs_total:
        dc_acc["Cost of Sale"] = dc_acc.get("Cost of Sale", 0.0) + cogs_total

    # Operating entries → opex
    for e in wb.operating_entries():
        if not _in_range(_txn_date(e.date), period_start, period_end):
            continue
        name = (e.description or e.vendor or "Operating Expense").strip()
        bucket = _classify(cat.get(name.lower()), default_bucket="operating_expenses")
        amt = _amount(e)
        if bucket == "direct_costs":
            dc_acc[name] += amt
        else:
            op_acc[name] += amt

    def _to_lines(d, classify_default):
        out = []
        for name, amt in sorted(d.items()):
            out.append(LineItem(account=name,
                                category=cat.get(name.lower()) or classify_default,
                                amount=amt))
        return out

    report.revenue = _to_lines(rev_acc, "Income")
    report.other_income = _to_lines(other_acc, "Other Income")
    report.direct_costs = _to_lines(dc_acc, "Direct Cost")
    report.operating_expenses = _to_lines(op_acc, "Operating Expenses")
    return report


def balance_sheet(wb: BizClinikWorkbook,
                  as_of: Optional[date] = None) -> BalanceSheetReport:
    """Derive what we can about the balance sheet from txn data alone.

    Computes:
      - Inventory at cost: sum over products of (net qty) × avg purchase cost
      - Output/Input VAT: from customer/supplier VAT columns
      - Retained earnings: net profit across the included period

    Cannot derive (and flagged in notes): cash/bank balances, trade
    receivables, trade payables, fixed assets, share capital — the BizClinik
    template doesn't carry payment/settlement data.
    """
    bs = BalanceSheetReport(as_of=as_of)

    avg_cost = _avg_unit_cost(wb, as_of=as_of)

    # Net qty on hand from inventory module (undated — treat as current).
    net_qty: dict[str, float] = defaultdict(float)
    for m in wb.inventory_movements():
        if not m.code:
            continue
        net_qty[m.code.strip()] += (m.qty_in or 0) - (m.qty_out or 0)

    inv_lines = []
    inv_total = 0.0
    no_cost_codes: list[str] = []
    for code, qty in sorted(net_qty.items()):
        cost = avg_cost.get(code, 0.0)
        value = qty * cost
        inv_total += value
        inv_lines.append({
            "code": code,
            "qty_on_hand": qty,
            "avg_unit_cost": cost,
            "value_at_cost": value,
        })
        if qty != 0 and cost == 0:
            no_cost_codes.append(code)
    bs.inventory_lines = inv_lines
    bs.inventory_at_cost = inv_total

    # VAT positions.
    bs.vat_payable = sum(_num(e.vat) for e in wb.customer_entries()
                         if not as_of or not _txn_date(e.date) or _txn_date(e.date) <= as_of)
    bs.vat_receivable = sum(_num(e.vat) for e in wb.supplier_entries()
                            if not as_of or not _txn_date(e.date) or _txn_date(e.date) <= as_of)

    # Retained earnings = net profit over all txns up to as_of.
    pnl = profit_and_loss(wb, period_end=as_of)
    bs.retained_earnings = pnl.net_profit

    bs.notes = [
        "Cash/bank, trade receivables, trade payables, fixed assets and share "
        "capital are NOT derivable from the BizClinik transaction modules — "
        "they require payment/settlement data the template does not carry.",
        "Inventory is valued at weighted-average purchase cost from Supplier "
        "Module rows posted to an inventory account (Chart of Accounts "
        "category in {Current Asset, Inventory, Stock}).",
        "Retained earnings = cumulative net profit from the P&L computation.",
    ]
    if no_cost_codes:
        bs.notes.append(
            "No purchase cost found for these product codes (valued at 0): "
            + ", ".join(no_cost_codes)
            + ". Add Supplier Module rows for them to value the stock."
        )
    return bs
