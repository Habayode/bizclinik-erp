"""Defense-in-depth around the double-entry invariant.

post_journal enforces DR==CR / non-negative / single-sided in Python and now
re-asserts balance from the persisted lines after flush. As a database-level
backstop, journal_line carries CHECK constraints (non-negative, single-sided)
so a write that bypasses the service layer on a freshly created database is
still rejected by the engine."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select


def _two_accounts(s):
    from bizclinik_erp.models import Account
    a = s.execute(select(Account).where(Account.code == "1130")).scalar_one()
    b = s.execute(select(Account).where(Account.code == "4300")).scalar_one()
    return a, b


def test_journal_line_check_constraints_declared():
    from bizclinik_erp.models import JournalLine
    names = {c.name for c in JournalLine.__table__.constraints if c.name}
    assert "ck_journal_line_debit_nonneg" in names
    assert "ck_journal_line_credit_nonneg" in names
    assert "ck_journal_line_single_sided" in names


def test_post_journal_rejects_unbalanced(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import JELine, post_journal
    with get_session() as s:
        a, b = _two_accounts(s)
        with pytest.raises(ValueError, match="unbalanced"):
            post_journal(s, date(2026, 1, 1), "bad",
                         [JELine(account_id=a.id, debit=100),
                          JELine(account_id=b.id, credit=90)])


def test_db_rejects_both_sided_line(fresh_db):
    """A single line carrying BOTH debit and credit is rejected by the DB CHECK
    even when inserted directly (bypassing post_journal)."""
    from sqlalchemy.exc import IntegrityError
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import JournalLine
    from bizclinik_erp.services.ledger import JELine, post_journal
    with get_session() as s:
        a, b = _two_accounts(s)
        je = post_journal(s, date(2026, 1, 1), "ok",
                          [JELine(account_id=a.id, debit=10),
                           JELine(account_id=b.id, credit=10)])
        bad = JournalLine(entry_id=je.id, account_id=a.id, debit=5, credit=5)
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()  # clear the failed transaction so the session closes clean


def test_db_rejects_negative_amount(fresh_db):
    from sqlalchemy.exc import IntegrityError
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import JournalLine
    from bizclinik_erp.services.ledger import JELine, post_journal
    with get_session() as s:
        a, b = _two_accounts(s)
        je = post_journal(s, date(2026, 1, 1), "ok",
                          [JELine(account_id=a.id, debit=10),
                           JELine(account_id=b.id, credit=10)])
        bad = JournalLine(entry_id=je.id, account_id=a.id, debit=-5, credit=0)
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()  # clear the failed transaction so the session closes clean


def test_balanced_post_persists_and_trial_balances(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import ledger
    from bizclinik_erp.services.ledger import JELine, post_journal
    with get_session() as s:
        a, b = _two_accounts(s)
        je = post_journal(s, date(2026, 1, 1), "ok",
                          [JELine(account_id=a.id, debit=1234.56),
                           JELine(account_id=b.id, credit=1234.56)])
        assert je.is_balanced
        rows = ledger.trial_balance(s)
        tot_dr = round(sum(r["debit"] for r in rows), 2)
        tot_cr = round(sum(r["credit"] for r in rows), 2)
        assert abs(tot_dr - tot_cr) < 0.01
