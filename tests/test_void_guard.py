"""reverse_journal must refuse to reverse an entry that already has a posted
reversal — otherwise a status flipped back to POSTED could be voided twice,
double-reversing the GL impact."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select


def test_double_reversal_is_blocked(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import post_journal, reverse_journal, JELine
    from bizclinik_erp.models import Account
    with get_session() as s:
        a1 = s.execute(select(Account).where(Account.code == "1210")).scalar_one().id
        a2 = s.execute(select(Account).where(Account.code == "1290")).scalar_one().id
        je = post_journal(s, date(2026, 1, 1), "test entry",
                          [JELine(account_id=a1, debit=100.0),
                           JELine(account_id=a2, credit=100.0)])
        rev = reverse_journal(s, je, date(2026, 1, 2), memo="void once")
        assert rev.entry_no
        with pytest.raises(ValueError, match="already been reversed"):
            reverse_journal(s, je, date(2026, 1, 3), memo="void twice")
