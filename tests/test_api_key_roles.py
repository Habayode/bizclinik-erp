"""Per-API-key roles: a key stores a role; the REST layer binds the request to
that role so the permission matrix limits what the key can do. Existing/default
keys are ADMIN (full access) for backward compatibility."""
from __future__ import annotations

import pytest


@pytest.fixture
def control_env(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(db_path))
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    from bizclinik_erp import tenancy, db as _db
    get_settings.cache_clear(); get_engine.cache_clear(); _session_factory.cache_clear()
    tenancy._reset_control_cache()
    from bizclinik_erp.services.bootstrap import bootstrap
    bootstrap(admin_password="x")
    tenancy.create_tenant("acme", "Acme Ltd", admin_password="pw")
    yield
    get_settings.cache_clear(); get_engine.cache_clear(); _session_factory.cache_clear()
    tenancy._reset_control_cache()
    _db.set_active_db_path(None)


def test_default_key_is_admin(control_env):
    from bizclinik_erp import tenancy
    key = tenancy.create_api_key("acme", "default key")
    assert tenancy.resolve_api_key(key)["role"] == "ADMIN"


def test_key_can_be_scoped_to_a_role(control_env):
    from bizclinik_erp import tenancy
    key = tenancy.create_api_key("acme", "reporting", role="VIEWER")
    assert tenancy.resolve_api_key(key)["role"] == "VIEWER"


def test_unknown_role_is_rejected(control_env):
    from bizclinik_erp import tenancy
    with pytest.raises(ValueError, match="Unknown role"):
        tenancy.create_api_key("acme", "bad", role="SUPERUSER")


def test_list_includes_role(control_env):
    from bizclinik_erp import tenancy
    tenancy.create_api_key("acme", "sales key", role="SALES")
    assert "SALES" in [k["role"] for k in tenancy.list_api_keys()]


def test_viewer_role_blocks_a_write_via_the_matrix(control_env):
    """The role a key carries, fed to the service authz layer, denies a write."""
    from bizclinik_erp import tenancy, authz
    key = tenancy.create_api_key("acme", "ro", role="VIEWER")
    role = tenancy.resolve_api_key(key)["role"]
    authz.set_actor_role(role)
    try:
        assert authz.has_perm("view.reports") is True
        with pytest.raises(authz.PermissionDenied):
            authz.require_perm("post.invoice")
    finally:
        authz.clear_actor()
