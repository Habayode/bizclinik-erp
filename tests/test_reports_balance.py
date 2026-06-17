"""Balance sheet stays balanced across fiscal years.

There is no year-end closing entry, so P&L accounts accrue across years. Equity
must therefore absorb ALL net income to date — prior years as Retained Earnings,
the current year as Current Year Earnings — or A = L + E breaks (this was the
"Balance Sheet: Off by prior-year profit" bug a school surfaced, since its
first term fell in the previous calendar year).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select


def _aid(s, code: str) -> int:
    from bizclinik_erp.models import Account
    return s.execute(select(Account).where(Account.code == code)).scalar_one().id


def test_balance_sheet_balances_with_prior_year_earnings(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import JELine, post_journal
    from bizclinik_erp.services import reports
    with get_session() as s:
        cash = _aid(s, "1110")
        sales = _aid(s, "4100")
        # Prior year (2025) profit of 800k: DR Cash / CR Sales.
        post_journal(s, date(2025, 9, 15), "Prior-year sale",
                     [JELine(account_id=cash, debit=800_000.0),
                      JELine(account_id=sales, credit=800_000.0)],
                     source_kind="OPENING")
        # Current year (2026) profit of 200k.
        post_journal(s, date(2026, 3, 10), "Current-year sale",
                     [JELine(account_id=cash, debit=200_000.0),
                      JELine(account_id=sales, credit=200_000.0)],
                     source_kind="INVOICE")

        bs = reports.balance_sheet(s, as_of=date(2026, 6, 30))
        assert bs["balanced"], bs
        assert bs["total_assets"] == 1_000_000.0
        eq = {r["name"]: r["amount"] for r in bs["equity"]}
        assert eq.get("Retained Earnings (prior years)") == 800_000.0
        assert eq.get("Current Year Earnings") == 200_000.0

        # The P&L for 2026 only sees the current-year sale.
        pnl = reports.profit_and_loss(s, period_start=date(2026, 1, 1),
                                      period_end=date(2026, 6, 30))
        assert pnl["total_revenue"] == 200_000.0


def test_balance_sheet_no_retained_line_when_no_prior_activity(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import JELine, post_journal
    from bizclinik_erp.services import reports
    with get_session() as s:
        cash = _aid(s, "1110")
        sales = _aid(s, "4100")
        post_journal(s, date(2026, 3, 10), "Current-year sale",
                     [JELine(account_id=cash, debit=200_000.0),
                      JELine(account_id=sales, credit=200_000.0)],
                     source_kind="INVOICE")
        bs = reports.balance_sheet(s, as_of=date(2026, 6, 30))
        assert bs["balanced"], bs
        names = {r["name"] for r in bs["equity"]}
        assert "Retained Earnings (prior years)" not in names
        assert "Current Year Earnings" in names
