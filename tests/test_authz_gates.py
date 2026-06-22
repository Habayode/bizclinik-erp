"""Service-layer authorization gates (defense-in-depth, not just page gates).

- void_invoice/void_bill/void_receipt/void_payment require 'void.any'.
- A MANUAL journal (post_journal with no source_kind) requires 'post.journal';
  service-driven postings (source_kind set) are gated by their own permission
  and pass through.

Role.SALES has post.invoice/post.receipt but neither void.any nor post.journal,
so it's the natural "allowed to trade, not to void/manual-post" actor. With no
actor bound (the default in most tests) authz is fail-open, so existing callers
are unaffected."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from bizclinik_erp import authz
from bizclinik_erp.authz import PermissionDenied
from bizclinik_erp.db import get_session
from bizclinik_erp.models import Account
from bizclinik_erp.services import voids
from bizclinik_erp.services.ledger import JELine, post_journal


def test_voids_require_void_any(fresh_db):
    authz.set_actor_role("SALES")  # no void.any
    try:
        with get_session() as s:
            for fn, name in [(voids.void_invoice, "invoice"), (voids.void_bill, "bill"),
                             (voids.void_receipt, "receipt"), (voids.void_payment, "payment")]:
                with pytest.raises(PermissionDenied):
                    fn(s, 999999, reason="unauthorized attempt")
    finally:
        authz.clear_actor()


def test_void_gate_passes_for_admin(fresh_db):
    authz.set_actor_role("ADMIN")  # has void.any
    try:
        with get_session() as s:
            # Gate passes -> proceeds to a genuine not-found ValueError (NOT PermissionDenied).
            with pytest.raises(ValueError) as ei:
                voids.void_invoice(s, 999999, reason="ok to try")
            assert not isinstance(ei.value, PermissionDenied)
    finally:
        authz.clear_actor()


def test_manual_journal_requires_post_journal(fresh_db):
    authz.set_actor_role("SALES")  # no post.journal
    lines = [JELine(account_id=1, debit=100.0), JELine(account_id=2, credit=100.0)]
    try:
        with get_session() as s:
            with pytest.raises(PermissionDenied):
                post_journal(s, date(2026, 1, 1), "manual entry", lines)  # source_kind=None
    finally:
        authz.clear_actor()


def test_service_posting_not_blocked_by_manual_gate(fresh_db):
    authz.set_actor_role("SALES")  # lacks post.journal, but source_kind is set
    try:
        with get_session() as s:
            ids = s.execute(select(Account.id).where(Account.is_postable == True).limit(2)).scalars().all()
            lines = [JELine(account_id=ids[0], debit=100.0),
                     JELine(account_id=ids[1], credit=100.0)]
            je = post_journal(s, date(2026, 1, 1), "service adjustment", lines,
                              source_kind="ADJUSTMENT")
            assert je.entry_no  # posted — the manual gate did not apply
    finally:
        authz.clear_actor()
