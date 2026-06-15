"""Service-layer authorization: the permission matrix is enforced inside the
services (not just the UI). A system context (no actor) is unrestricted so
CLI/jobs/tests keep working; an explicit role is held to its permissions."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _clear_actor():
    from bizclinik_erp import authz
    authz.clear_actor()
    yield
    authz.clear_actor()


def _accounts(s):
    from bizclinik_erp.models import Account
    a1 = s.execute(select(Account).where(Account.code == "1210")).scalar_one().id
    a2 = s.execute(select(Account).where(Account.code == "1290")).scalar_one().id
    return a1, a2


def test_system_context_is_unrestricted(fresh_db):
    from bizclinik_erp import authz
    assert authz.current_role() is None
    assert authz.has_perm("reset.db") is True
    authz.require_perm("reset.db")          # must not raise


def test_role_without_perm_is_blocked_in_service(fresh_db):
    from bizclinik_erp import authz
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sv
    from bizclinik_erp.models import Customer
    with get_session() as s:
        c = Customer(code="C1", name="X Ltd"); s.add(c); s.flush(); cid = c.id
    # AP role: has post.bill/post.payment, NOT post.invoice.
    authz.set_actor_role("AP")
    with get_session() as s:
        with pytest.raises(authz.PermissionDenied):
            sv.issue_invoice(s, customer_id=cid, invoice_date=date(2026, 1, 1),
                             lines=[sv.LineInput(product_id=None, description="svc",
                                                 qty=1.0, unit_price=100.0, tax_rate=0.0)])


def test_role_with_perm_passes_in_service(fresh_db):
    from bizclinik_erp import authz
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sv
    from bizclinik_erp.models import Customer, DocStatus
    with get_session() as s:
        c = Customer(code="C2", name="Y Ltd"); s.add(c); s.flush(); cid = c.id
    authz.set_actor_role("SALES")           # SALES has post.invoice
    with get_session() as s:
        inv = sv.issue_invoice(s, customer_id=cid, invoice_date=date(2026, 1, 1),
                               lines=[sv.LineInput(product_id=None, description="svc",
                                                   qty=1.0, unit_price=100.0, tax_rate=0.0)])
        assert inv.status == DocStatus.POSTED


def test_only_admin_can_reopen_period(fresh_db):
    from bizclinik_erp import authz
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import fiscal
    with get_session() as s:        # close as system (unrestricted)
        fiscal.close_period(s, 2026, 1)
    authz.set_actor_role("ACCOUNTANT")      # no reopen.period
    with get_session() as s:
        with pytest.raises(authz.PermissionDenied):
            fiscal.reopen_period(s, 2026, 1, reason="adjustment needed")
    authz.set_actor_role("ADMIN")
    with get_session() as s:
        p = fiscal.reopen_period(s, 2026, 1, reason="adjustment needed")
        assert p.status.value == "OPEN"


def test_closed_period_blocks_posting(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import fiscal
    from bizclinik_erp.services.fiscal import PeriodClosedError
    from bizclinik_erp.services.ledger import post_journal, JELine
    with get_session() as s:
        fiscal.close_period(s, 2026, 3)
    with get_session() as s:
        a1, a2 = _accounts(s)
        with pytest.raises(PeriodClosedError):
            post_journal(s, date(2026, 3, 15), "blocked",
                         [JELine(account_id=a1, debit=10.0),
                          JELine(account_id=a2, credit=10.0)])
