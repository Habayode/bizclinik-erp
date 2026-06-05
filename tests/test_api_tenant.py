"""Per-tenant API key tests: a key sees only its tenant's data."""
from __future__ import annotations

import pytest


@pytest.fixture
def api_env(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(db_path))
    monkeypatch.delenv("BIZCLINIK_API_KEY", raising=False)
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    from bizclinik_erp import tenancy, db as _db
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
    tenancy._reset_control_cache()
    yield tmp_path
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
    tenancy._reset_control_cache()
    _db.set_active_db_path(None)


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_no_key_rejected(api_env):
    c = _client()
    assert c.get("/api/v1/customers").status_code == 401


def test_invalid_key_rejected(api_env):
    c = _client()
    r = c.get("/api/v1/customers", headers={"X-API-Key": "bogus"})
    assert r.status_code == 401


def test_per_tenant_key_isolation(api_env):
    from bizclinik_erp import tenancy
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Customer

    # Two tenants with one customer each
    tenancy.create_tenant("alpha", "Alpha Co", admin_password="pw")
    tenancy.create_tenant("beta", "Beta Co", admin_password="pw")
    tenancy.set_active("alpha")
    with get_session() as s:
        s.add(Customer(code="A1", name="Alpha Customer"))
    tenancy.set_active("beta")
    with get_session() as s:
        s.add(Customer(code="B1", name="Beta Customer"))
    tenancy.set_active(None)

    key_a = tenancy.create_api_key("alpha", "alpha key")
    key_b = tenancy.create_api_key("beta", "beta key")

    c = _client()

    # whoami reflects the key's tenant
    assert c.get("/api/v1/whoami", headers={"X-API-Key": key_a}).json()["tenant"] == "alpha"
    assert c.get("/api/v1/whoami", headers={"X-API-Key": key_b}).json()["tenant"] == "beta"

    # Each key sees ONLY its tenant's customers
    ca = c.get("/api/v1/customers", headers={"X-API-Key": key_a}).json()
    cb = c.get("/api/v1/customers", headers={"X-API-Key": key_b}).json()
    names_a = {x["name"] for x in ca}
    names_b = {x["name"] for x in cb}
    assert "Alpha Customer" in names_a and "Beta Customer" not in names_a
    assert "Beta Customer" in names_b and "Alpha Customer" not in names_b


def test_create_invoice_isolated_to_tenant(api_env):
    from bizclinik_erp import tenancy
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Customer, Product

    tenancy.create_tenant("acme", "Acme", admin_password="pw")
    tenancy.set_active("acme")
    with get_session() as s:
        s.add(Customer(code="CUST", name="Acme Buyer"))
        s.add(Product(sku="SKU1", name="Thing", standard_price=500, is_stockable=False))
    tenancy.set_active(None)
    key = tenancy.create_api_key("acme", "acme key")

    c = _client()
    r = c.post("/api/v1/invoices", headers={"X-API-Key": key}, json={
        "customer_code": "CUST",
        "invoice_date": "2026-06-01",
        "lines": [{"sku": "SKU1", "qty": 2, "unit_price": 500, "tax_rate": 0.075}],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["customer"] == "Acme Buyer"
    assert round(body["total"], 2) == 1075.00  # 1000 + 7.5% VAT

    # The invoice exists for this key, and the trial balance is balanced
    tb = c.get("/api/v1/reports/trial-balance", headers={"X-API-Key": key}).json()
    assert tb["balanced"] is True


def test_legacy_env_key_uses_default_db(api_env, monkeypatch):
    monkeypatch.setenv("BIZCLINIK_API_KEY", "legacy-secret")
    # Bootstrap the default DB
    from bizclinik_erp.services.bootstrap import bootstrap
    bootstrap(admin_password="x")
    c = _client()
    r = c.get("/api/v1/whoami", headers={"X-API-Key": "legacy-secret"})
    assert r.status_code == 200
    assert r.json()["tenant"] is None
