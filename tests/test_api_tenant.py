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


def _activate_business(slug):
    """Give a tenant an active Business subscription (the REST API is a
    Business-tier entitlement, so API tests must subscribe first)."""
    from datetime import datetime, timedelta
    from bizclinik_erp import tenancy
    from bizclinik_erp.services import billing
    fac = tenancy._control_factory()
    with fac() as s:
        billing._upsert_subscription(
            s, tenant_slug=slug, plan_code="business", status="active",
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30))
        s.commit()


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
    _activate_business("alpha")
    _activate_business("beta")
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
    _activate_business("acme")
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


def test_viewer_key_can_read_but_not_write(api_env):
    """A VIEWER-scoped key reads fine but is blocked (403) from posting — the
    service-layer authz enforces the key's role end-to-end through the API."""
    from bizclinik_erp import tenancy
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Customer, Product

    tenancy.create_tenant("acme", "Acme", admin_password="pw")
    _activate_business("acme")
    tenancy.set_active("acme")
    with get_session() as s:
        s.add(Customer(code="CUST", name="Acme Buyer"))
        s.add(Product(sku="SKU1", name="Thing", standard_price=500, is_stockable=False))
    tenancy.set_active(None)

    viewer = tenancy.create_api_key("acme", "reporting", role="VIEWER")
    admin = tenancy.create_api_key("acme", "ops", role="ADMIN")
    c = _client()
    payload = {"customer_code": "CUST", "invoice_date": "2026-06-01",
               "lines": [{"sku": "SKU1", "qty": 1, "unit_price": 500, "tax_rate": 0.0}]}

    # VIEWER: read OK, write forbidden.
    assert c.get("/api/v1/customers", headers={"X-API-Key": viewer}).status_code == 200
    r = c.post("/api/v1/invoices", headers={"X-API-Key": viewer}, json=payload)
    assert r.status_code == 403, r.text

    # ADMIN key on the same tenant can write.
    r = c.post("/api/v1/invoices", headers={"X-API-Key": admin}, json=payload)
    assert r.status_code == 201, r.text


def test_viewer_key_blocked_on_writes_across_modules(api_env):
    """Every mutating REST endpoint must reject a VIEWER key (403): bank
    statements, CRM lead create, billing subscribe, and statement email — not
    just invoices. An ADMIN key still succeeds."""
    from sqlalchemy import select
    from bizclinik_erp import tenancy
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Customer, BankAccount

    tenancy.create_tenant("acme", "Acme", admin_password="pw")
    _activate_business("acme")
    tenancy.set_active("acme")
    with get_session() as s:
        s.add(Customer(code="CUST", name="Buyer"))
        s.flush()
        bank_id = s.execute(select(BankAccount.id)).scalars().first()  # a seeded bank
    tenancy.set_active(None)

    viewer = tenancy.create_api_key("acme", "ro", role="VIEWER")
    admin = tenancy.create_api_key("acme", "ops", role="ADMIN")
    c = _client()
    hv = {"X-API-Key": viewer}

    assert c.post("/api/v1/crm/leads", headers=hv,
                  json={"name": "Lead Co"}).status_code == 403
    assert c.post("/api/v1/billing/subscribe", headers=hv,
                  json={"tenant_slug": "acme", "plan_code": "business",
                        "email": "a@b.com"}).status_code == 403
    assert c.post("/api/v1/customers/statement/email", headers=hv,
                  json={"customer_code": "CUST", "period_start": "2026-01-01",
                        "period_end": "2026-12-31"}).status_code == 403
    assert c.post("/api/v1/bank/statements", headers=hv,
                  json={"bank_account_id": bank_id, "period_start": "2026-01-01",
                        "period_end": "2026-01-31",
                        "lines": [{"txn_date": "2026-01-05", "description": "x",
                                   "amount": 100.0}]}).status_code == 403

    # ADMIN key still works.
    assert c.post("/api/v1/crm/leads", headers={"X-API-Key": admin},
                  json={"name": "Lead Co"}).status_code == 201


def test_legacy_env_key_uses_default_db(api_env, monkeypatch):
    monkeypatch.setenv("BIZCLINIK_API_KEY", "legacy-secret")
    # Bootstrap the default DB
    from bizclinik_erp.services.bootstrap import bootstrap
    bootstrap(admin_password="x")
    c = _client()
    r = c.get("/api/v1/whoami", headers={"X-API-Key": "legacy-secret"})
    assert r.status_code == 200
    assert r.json()["tenant"] is None


def test_api_requires_business_plan(api_env):
    """A tenant without a Business subscription (Free) is blocked from the API
    with HTTP 402; activating Business unlocks it."""
    from bizclinik_erp import tenancy
    tenancy.create_tenant("freeco", "Free Co", admin_password="pw")
    tenancy.set_active(None)
    key = tenancy.create_api_key("freeco", "free key")
    c = _client()

    # Free tenant -> 402 Payment Required.
    r = c.get("/api/v1/customers", headers={"X-API-Key": key})
    assert r.status_code == 402, r.text

    # Activate Business -> now allowed.
    _activate_business("freeco")
    r = c.get("/api/v1/customers", headers={"X-API-Key": key})
    assert r.status_code == 200, r.text


def test_billing_endpoints_reject_cross_tenant(api_env):
    """A tenant-scoped key may read/modify only its OWN subscription. Passing
    another tenant's slug must 403 (was a cross-tenant leak)."""
    from bizclinik_erp import tenancy
    tenancy.create_tenant("alpha", "Alpha Co", admin_password="pw")
    tenancy.create_tenant("beta", "Beta Co", admin_password="pw")
    _activate_business("alpha")
    _activate_business("beta")
    tenancy.set_active(None)
    key_a = tenancy.create_api_key("alpha", "alpha key")
    c = _client()

    # alpha's key reading its OWN status: allowed.
    own = c.get("/api/v1/billing/status?tenant_slug=alpha",
                headers={"X-API-Key": key_a})
    assert own.status_code == 200, own.text

    # alpha's key probing beta's status: forbidden.
    cross = c.get("/api/v1/billing/status?tenant_slug=beta",
                  headers={"X-API-Key": key_a})
    assert cross.status_code == 403, cross.text

    # alpha's key trying to change beta's plan: forbidden.
    sub = c.post("/api/v1/billing/subscribe",
                 headers={"X-API-Key": key_a},
                 json={"tenant_slug": "beta", "plan_code": "business",
                       "email": "x@example.com"})
    assert sub.status_code == 403, sub.text
