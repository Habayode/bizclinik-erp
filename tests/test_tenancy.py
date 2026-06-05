"""Multi-tenant isolation tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select


@pytest.fixture
def tenant_env(monkeypatch, tmp_path):
    """Fresh control plane + tenant area under a temp dir."""
    db_path = tmp_path / "legacy.db"
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(db_path))
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    from bizclinik_erp import tenancy
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
    tenancy._reset_control_cache()
    yield tmp_path
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
    tenancy._reset_control_cache()
    from bizclinik_erp import db as _db
    _db.set_active_db_path(None)


def test_no_tenants_uses_legacy(tenant_env):
    from bizclinik_erp import tenancy
    assert tenancy.has_tenants() is False


def test_create_tenant_bootstraps_db(tenant_env):
    from bizclinik_erp import tenancy
    from bizclinik_erp.db import get_session, set_active_db_path
    from bizclinik_erp.models import Account, User

    t = tenancy.create_tenant("acme", "Acme Ltd", admin_password="pw1")
    assert t["slug"] == "acme"
    assert tenancy.has_tenants() is True

    # The tenant DB should have the seeded COA + admin user.
    set_active_db_path(t["db_path"])
    with get_session() as s:
        assert s.query(Account).count() > 0
        assert s.query(User).filter(User.username == "admin").count() == 1
    set_active_db_path(None)


def test_tenant_isolation(tenant_env):
    from bizclinik_erp import tenancy
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Customer

    tenancy.create_tenant("alpha", "Alpha Co", admin_password="pw")
    tenancy.create_tenant("beta", "Beta Co", admin_password="pw")

    # Add a customer in each tenant
    tenancy.set_active("alpha")
    with get_session() as s:
        s.add(Customer(code="A1", name="Alpha Customer"))
    tenancy.set_active("beta")
    with get_session() as s:
        s.add(Customer(code="B1", name="Beta Customer"))

    # Alpha sees only Alpha
    tenancy.set_active("alpha")
    with get_session() as s:
        names = [c.name for c in s.execute(select(Customer)).scalars()]
        assert names == ["Alpha Customer"]

    # Beta sees only Beta
    tenancy.set_active("beta")
    with get_session() as s:
        names = [c.name for c in s.execute(select(Customer)).scalars()]
        assert names == ["Beta Customer"]


def test_duplicate_slug_rejected(tenant_env):
    from bizclinik_erp import tenancy
    tenancy.create_tenant("dup", "Dup One", admin_password="pw")
    with pytest.raises(ValueError):
        tenancy.create_tenant("dup", "Dup Two", admin_password="pw")


def test_invalid_slug_rejected(tenant_env):
    from bizclinik_erp import tenancy
    # Note: slugs are normalised to lowercase, so "UPPER" -> "upper" is VALID.
    for bad in ["x", "Has Space", "bad_underscore", "", "-leading", "a@b"]:
        with pytest.raises(ValueError):
            tenancy.create_tenant(bad, "Name", admin_password="pw")


def test_set_active_none_falls_back_to_legacy(tenant_env):
    from bizclinik_erp import tenancy
    from bizclinik_erp.db import get_active_db_path
    tenancy.create_tenant("gamma", "Gamma", admin_password="pw")
    tenancy.set_active("gamma")
    assert get_active_db_path() is not None
    tenancy.set_active(None)
    assert get_active_db_path() is None
