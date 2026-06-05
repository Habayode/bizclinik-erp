"""Month-End Close service tests: accruals, prepaid amortisation, deferred
revenue, the computed close checklist, and accrual reversal — all verified
to keep the trial balance in balance."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select


def _account_id(s, code: str) -> int:
    from bizclinik_erp.models import Account
    return s.execute(select(Account).where(Account.code == code)).scalar_one().id


def _line_for(je, account_id: int):
    for l in je.lines:
        if l.account_id == account_id:
            return l
    return None


def _tb_balanced(s, as_of=None) -> bool:
    from bizclinik_erp.services.ledger import trial_balance
    rows = trial_balance(s, as_of=as_of)
    tot_dr = round(sum(r["debit"] for r in rows), 2)
    tot_cr = round(sum(r["credit"] for r in rows), 2)
    return abs(tot_dr - tot_cr) < 0.01


def test_accrue_expense_posts_balanced_dr_expense_cr_2160(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import closing

    with get_session() as s:
        exp_id = _account_id(s, "6200")  # Rent & Utilities
        accrued_id = _account_id(s, "2160")
        je = closing.accrue_expense(
            s, on=date(2026, 6, 30), amount=150_000.0,
            expense_account_id=exp_id, memo="June rent accrual")

        assert je.is_balanced
        assert je.source_kind == "ACCRUAL"
        exp_line = _line_for(je, exp_id)
        accr_line = _line_for(je, accrued_id)
        assert exp_line is not None and accr_line is not None
        assert exp_line.debit == pytest.approx(150_000.0)
        assert exp_line.credit == 0.0
        assert accr_line.credit == pytest.approx(150_000.0)
        assert accr_line.debit == 0.0
        assert _tb_balanced(s)


def test_amortize_prepaid_posts_balanced_dr_expense_cr_1170(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import closing

    with get_session() as s:
        exp_id = _account_id(s, "6200")
        prepaid_id = _account_id(s, "1170")
        je = closing.amortize_prepaid(
            s, on=date(2026, 6, 30), amount=40_000.0,
            expense_account_id=exp_id, memo="Insurance amortisation")

        assert je.is_balanced
        assert je.source_kind == "PREPAID_AMORT"
        exp_line = _line_for(je, exp_id)
        prep_line = _line_for(je, prepaid_id)
        assert exp_line.debit == pytest.approx(40_000.0)
        assert prep_line.credit == pytest.approx(40_000.0)
        assert _tb_balanced(s)


def test_close_checklist_trial_balance_ok_after_balanced_opening_je(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import closing
    from bizclinik_erp.services.ledger import JELine, post_journal

    with get_session() as s:
        # Balanced opening JE: DR Cash (1000) / CR Owner's equity-ish (4100 sales
        # just to give the TB nonzero, balanced activity).
        cash_id = _account_id(s, "1110")
        sales_id = _account_id(s, "4100")
        post_journal(
            s, date(2026, 6, 15), "Opening balanced JE",
            [JELine(account_id=cash_id, debit=500_000.0),
             JELine(account_id=sales_id, credit=500_000.0)],
            source_kind="OPENING",
        )

        checklist = closing.close_checklist(s, year=2026, month=6)
        assert isinstance(checklist, list)
        tb_item = next(i for i in checklist if i["task"] == "Trial balance balances")
        assert tb_item["status"] == "ok", tb_item
        # Sanity: every item carries the required keys.
        for item in checklist:
            assert {"task", "status", "detail"} <= set(item)
            assert item["status"] in {"ok", "pending", "na"}


def test_reverse_accrual_is_equal_and_opposite_tb_balanced(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import closing

    with get_session() as s:
        exp_id = _account_id(s, "6200")
        accrued_id = _account_id(s, "2160")
        accrual = closing.accrue_expense(
            s, on=date(2026, 6, 30), amount=90_000.0,
            expense_account_id=exp_id, memo="Accrual to reverse")
        accrual_id = accrual.id

    with get_session() as s:
        rev = closing.reverse_accrual(s, accrual_je_id=accrual_id,
                                      on=date(2026, 7, 1))
        assert rev.is_balanced
        # Equal and opposite: expense now credited, accrual now debited.
        exp_line = _line_for(rev, exp_id)
        accr_line = _line_for(rev, accrued_id)
        assert exp_line.credit == pytest.approx(90_000.0)
        assert accr_line.debit == pytest.approx(90_000.0)
        # Net effect across both JEs leaves the TB balanced and flat.
        assert _tb_balanced(s)
        from bizclinik_erp.services.ledger import account_balance
        assert account_balance(s, exp_id) == pytest.approx(0.0, abs=0.01)
        assert account_balance(s, accrued_id) == pytest.approx(0.0, abs=0.01)
