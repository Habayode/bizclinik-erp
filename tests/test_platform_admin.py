"""Platform-operator isolation: a tenant admin must never see or touch the
global tenant registry. Covers (1) the pure allow-list evaluator, including the
dangerous case where every tenant's bootstrap user is named 'admin'; (2) nav
hiding of the Tenants console; (3) service-layer enforcement so create/mutate of
tenants + API keys is blocked for a bound tenant actor regardless of entry point.
"""
from __future__ import annotations

import pytest

from bizclinik_erp.auth import evaluate_platform_admin
from bizclinik_erp.nav import build_nav_spec


# --------------------------------------------------------------------------- #
# Pure allow-list evaluator                                                   #
# --------------------------------------------------------------------------- #

def _ev(**kw):
    base = dict(principals=[], active_tenant=None, username=None, role=None,
                logged_in=True, has_tenants=True)
    base.update(kw)
    return evaluate_platform_admin(**base)


def test_operator_principal_matches_own_tenant():
    assert _ev(principals=["hagai:admin"], active_tenant="hagai",
               username="admin", role="ADMIN") is True


def test_tenant_admin_with_same_username_is_denied():
    # The school is handed otasch:admin. It must NOT match a hagai:admin entry,
    # even though both usernames are 'admin'. This is the whole point.
    assert _ev(principals=["hagai:admin"], active_tenant="otasch",
               username="admin", role="ADMIN") is False


def test_wrong_username_in_operator_tenant_denied():
    assert _ev(principals=["hagai:admin"], active_tenant="hagai",
               username="viewer", role="VIEWER") is False


def test_not_logged_in_is_never_operator():
    assert _ev(principals=["hagai:admin"], active_tenant="hagai",
               username="admin", role="ADMIN", logged_in=False) is False


def test_empty_allowlist_multitenant_fails_closed():
    # Tenants exist + no allow-list configured => nobody is operator.
    assert _ev(principals=[], has_tenants=True, active_tenant="hagai",
               username="admin", role="ADMIN") is False


def test_empty_allowlist_single_tenant_admin_is_operator():
    # No registry to leak yet: the lone admin runs the box (and creates the
    # first tenant from the Tenants page).
    assert _ev(principals=[], has_tenants=False, active_tenant=None,
               username="admin", role="ADMIN") is True
    assert _ev(principals=[], has_tenants=False, active_tenant=None,
               username="bob", role="VIEWER") is False


def test_bare_username_only_in_single_tenant_mode():
    # Honoured when no tenants exist...
    assert _ev(principals=["ops"], has_tenants=False, active_tenant=None,
               username="ops", role="ADMIN") is True
    # ...ignored once tenants exist (H3: active_tenant None is ambiguous then).
    assert _ev(principals=["ops"], has_tenants=True, active_tenant=None,
               username="ops", role="ADMIN") is False
    # ...and never matches when a tenant is active.
    assert _ev(principals=["ops"], has_tenants=False, active_tenant="x",
               username="ops", role="ADMIN") is False


def test_multiple_principals_any_match():
    assert _ev(principals=["hagai:admin", "ops:root"], active_tenant="ops",
               username="root", role="ADMIN") is True


# --------------------------------------------------------------------------- #
# Nav hiding (cosmetic, but must default to hidden)                           #
# --------------------------------------------------------------------------- #

def _paths(spec):
    return [p["path"] for _, pages in spec for p in pages]


@pytest.mark.parametrize("vertical", ["general", "school"])
def test_tenants_hidden_for_non_operator(vertical):
    assert not any("21_Tenants" in p
                   for p in _paths(build_nav_spec(vertical, platform_admin=False)))


@pytest.mark.parametrize("vertical", ["general", "school"])
def test_tenants_visible_for_operator(vertical):
    assert any("21_Tenants" in p
               for p in _paths(build_nav_spec(vertical, platform_admin=True)))


def test_tenants_hidden_by_default():
    # Safe default: omitting the flag must NOT expose the operator console.
    assert not any("21_Tenants" in p for p in _paths(build_nav_spec("general")))
    # Billing (per-tenant, legitimate) stays for everyone.
    assert any("22_Billing" in p for p in _paths(build_nav_spec("general")))


# --------------------------------------------------------------------------- #
# Service-layer enforcement (defence in depth, any entry point)               #
# --------------------------------------------------------------------------- #

@pytest.fixture
def tenant_env(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(db_path))
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    from bizclinik_erp import tenancy
    get_settings.cache_clear(); get_engine.cache_clear()
    _session_factory.cache_clear(); tenancy._reset_control_cache()
    yield tmp_path
    get_settings.cache_clear(); get_engine.cache_clear()
    _session_factory.cache_clear(); tenancy._reset_control_cache()
    from bizclinik_erp import db as _db
    _db.set_active_db_path(None)


def test_create_tenant_blocked_for_tenant_admin(tenant_env):
    from bizclinik_erp import tenancy, authz
    authz.set_actor_role("ADMIN")          # a bound tenant admin (not operator)
    with pytest.raises(authz.PlatformAdminRequired):
        tenancy.create_tenant("evil", "Evil Co", admin_password="pw")


def test_create_api_key_blocked_for_tenant_admin(tenant_env):
    from bizclinik_erp import tenancy, authz
    # A legitimate tenant exists (created as system/no-actor).
    tenancy.create_tenant("acme", "Acme Ltd", admin_password="pw")
    authz.set_actor_role("ADMIN")
    with pytest.raises(authz.PlatformAdminRequired):
        tenancy.create_api_key("acme", "stolen key")


def test_no_actor_is_breakglass(tenant_env):
    # CLI / scripts / migrations run with no bound actor → allowed.
    from bizclinik_erp import tenancy
    t = tenancy.create_tenant("cli", "CLI Co", admin_password="pw")
    assert t["slug"] == "cli"


def test_platform_operator_can_mutate(tenant_env):
    from bizclinik_erp import tenancy, authz
    authz.set_actor_role("ADMIN")
    authz.set_platform_admin(True)          # an allow-listed operator session
    t = tenancy.create_tenant("ok", "Okay Co", admin_password="pw")
    assert t["slug"] == "ok"
    key = tenancy.create_api_key("ok", "ops key")
    assert key.startswith("bzk_")
