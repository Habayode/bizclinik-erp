"""Authz fails CLOSED for an interactive request that never bound an actor, but
keeps the break-glass for genuine system/CLI/job/test contexts.

The web (auth.require_login) and REST API (require_api_key) call
authz.set_request_context(True) at their boundary; CLI / scheduled jobs / seed /
migrations / tests never do, so they remain unrestricted."""
from __future__ import annotations

import pytest

from bizclinik_erp import authz
from bizclinik_erp.authz import PermissionDenied, PlatformAdminRequired


def test_breakglass_when_not_in_request_context():
    authz.clear_actor()  # no role, not a request -> system/CLI/test break-glass
    assert authz.has_perm("post.journal") is True
    authz.require_perm("post.journal")   # no raise
    authz.require_platform()             # no raise


def test_fail_closed_unbound_in_request_context():
    authz.set_request_context(True)      # interactive request, but no role bound
    try:
        assert authz.has_perm("post.journal") is False
        with pytest.raises(PermissionDenied):
            authz.require_perm("post.journal")
        with pytest.raises(PlatformAdminRequired):
            authz.require_platform()
    finally:
        authz.clear_actor()


def test_bound_role_in_request_context_uses_matrix():
    authz.set_request_context(True)
    authz.set_actor_role("SALES")        # has post.invoice, not void.any
    try:
        assert authz.has_perm("post.invoice") is True
        assert authz.has_perm("void.any") is False
        with pytest.raises(PermissionDenied):
            authz.require_perm("void.any")
    finally:
        authz.clear_actor()


def test_clear_actor_resets_request_context():
    authz.set_request_context(True)
    authz.set_actor_role("SALES")
    authz.clear_actor()
    assert authz.current_role() is None
    assert authz.has_perm("anything") is True  # back to break-glass
