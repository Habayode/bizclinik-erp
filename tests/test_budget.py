"""Tests for budgets + budget-vs-actual variance reporting."""
from __future__ import annotations

from datetime import date

import pytest


def _acct_id(s, code: str) -> int:
    from bizclinik_erp.models import Account
    from sqlalchemy import select
    return s.execute(select(Account).where(Account.code == code)).scalar_one().id


def test_budget_vs_actual_totals_and_variance(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import budget as bud
    from bizclinik_erp.services.ledger import post_journal, JELine

    with get_session() as s:
        b = bud.create_budget(s, name="FY2026", year=2026)
        budget_id = b.id
        sal = _acct_id(s, "6100")   # Salaries & Wages (EXPENSE)
        cash = _acct_id(s, "1110")  # a cash/bank account for the credit side

    # Budget 100,000 to Salaries for Jan, Feb, Mar.
    with get_session() as s:
        bud.bulk_set(s, budget_id, [
            {"account_id": sal, "month": 1, "amount": 100_000},
            {"account_id": sal, "month": 2, "amount": 100_000},
            {"account_id": sal, "month": 3, "amount": 100_000},
        ])

    # Post an actual salary expense of 250,000 in February.
    with get_session() as s:
        post_journal(s, date(2026, 2, 15), "Feb salaries",
                     [JELine(account_id=sal, debit=250_000),
                      JELine(account_id=cash, credit=250_000)])

    with get_session() as s:
        rows = bud.budget_vs_actual(
            s, budget_id,
            period_start=date(2026, 1, 1), period_end=date(2026, 3, 31))

    assert len(rows) == 1
    row = rows[0]
    assert row["code"] == "6100"
    assert row["budget_total"] == 300_000
    assert row["actual_total"] == 250_000
    assert row["variance"] == -50_000


def test_variance_pct_computed(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import budget as bud
    from bizclinik_erp.services.ledger import post_journal, JELine

    with get_session() as s:
        b = bud.create_budget(s, name="FY2026", year=2026)
        budget_id = b.id
        sal = _acct_id(s, "6100")
        cash = _acct_id(s, "1110")

    with get_session() as s:
        bud.bulk_set(s, budget_id, [
            {"account_id": sal, "month": 1, "amount": 100_000},
            {"account_id": sal, "month": 2, "amount": 100_000},
            {"account_id": sal, "month": 3, "amount": 100_000},
        ])

    with get_session() as s:
        post_journal(s, date(2026, 2, 15), "Feb salaries",
                     [JELine(account_id=sal, debit=250_000),
                      JELine(account_id=cash, credit=250_000)])

    with get_session() as s:
        rows = bud.budget_vs_actual(
            s, budget_id,
            period_start=date(2026, 1, 1), period_end=date(2026, 3, 31))

    # (250000 - 300000) / 300000 * 100 = -16.67
    assert rows[0]["variance_pct"] == pytest.approx(-16.67, abs=0.01)


def test_variance_pct_divide_by_zero_guarded(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import budget as bud
    from bizclinik_erp.services.ledger import post_journal, JELine

    with get_session() as s:
        b = bud.create_budget(s, name="FY2026", year=2026)
        budget_id = b.id
        sal = _acct_id(s, "6100")
        cash = _acct_id(s, "1110")

    # Budget of zero for the account.
    with get_session() as s:
        bud.set_budget_line(s, budget_id, sal, month=1, amount=0.0)

    # Post an actual so there's something to compare.
    with get_session() as s:
        post_journal(s, date(2026, 1, 10), "Jan salaries",
                     [JELine(account_id=sal, debit=50_000),
                      JELine(account_id=cash, credit=50_000)])

    with get_session() as s:
        rows = bud.budget_vs_actual(
            s, budget_id,
            period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))

    assert rows[0]["budget_total"] == 0
    assert rows[0]["actual_total"] == 50_000
    assert rows[0]["variance"] == 50_000
    assert rows[0]["variance_pct"] == 0.0  # guarded, no ZeroDivisionError
