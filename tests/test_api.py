"""Tests for the FastAPI REST layer (api.main).

The API reuses the same services + DB as the Streamlit app, so we lean on the
shared ``fresh_db`` fixture (temp sqlite, seeded chart of accounts) from
conftest.py. ``BIZCLINIK_API_KEY`` is set via monkeypatch so require_api_key
authenticates instead of returning 503.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import app

API_KEY = "testkey"
AUTH = {"X-API-Key": API_KEY}


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.setenv("BIZCLINIK_API_KEY", API_KEY)
    # No webhook URLs -> fire() is a silent no-op during tests.
    monkeypatch.delenv("BIZCLINIK_WEBHOOK_URLS", raising=False)
    return TestClient(app)


def _seed_customer_and_product():
    """Add one customer + one (non-stockable, to avoid COGS plumbing) product."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Customer, Product

    with get_session() as s:
        s.add(Customer(code="CUST1", name="Acme Ltd", email="acme@example.com"))
        s.add(Product(
            sku="SKU1", name="Consulting Hour", unit="hr",
            standard_price=100.0, is_stockable=False,
        ))


def _seed_bank_account() -> int:
    """Return a usable bank account id — reuse a seeded one, else create one."""
    from sqlalchemy import select
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Account, BankAccount
    with get_session() as s:
        existing = s.execute(select(BankAccount)).scalars().first()
        if existing:
            return existing.id
        acct = s.execute(select(Account).where(Account.is_postable == True)  # noqa: E712
                         ).scalars().first()
        ba = BankAccount(code="BANKFEED_TEST", name="Main Current",
                         bank="GTBank", gl_account_id=acct.id)
        s.add(ba)
        s.flush()
        return ba.id


def test_health_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_bank_feed_ingest_lines(client):
    bank_id = _seed_bank_account()
    payload = {
        "bank_account_id": bank_id,
        "period_start": date(2026, 5, 1).isoformat(),
        "period_end": date(2026, 5, 31).isoformat(),
        "opening_balance": 0.0,
        "closing_balance": 4500.0,
        "source": "mono-aggregator",
        "lines": [
            {"txn_date": date(2026, 5, 2).isoformat(), "description": "Inflow",
             "amount": 5000.0, "reference": "R1"},
            {"txn_date": date(2026, 5, 5).isoformat(), "description": "Charge",
             "amount": -500.0, "reference": "R2"},
        ],
    }
    resp = client.post("/api/v1/bank/statements", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["lines_imported"] == 2
    assert body["statement_id"] > 0
    assert "summary" in body


def test_bank_feed_ingest_csv(client):
    bank_id = _seed_bank_account()
    csv = ("Trans Date,Narration,Debit,Credit\n"
           "02/05/2026,POS,1000,\n"
           "04/05/2026,Transfer in,,7500\n")
    payload = {
        "bank_account_id": bank_id,
        "period_start": date(2026, 5, 1).isoformat(),
        "period_end": date(2026, 5, 31).isoformat(),
        "closing_balance": 6500.0,
        "csv": csv,
    }
    resp = client.post("/api/v1/bank/statements", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    assert resp.json()["lines_imported"] == 2


def test_bank_feed_requires_key(client):
    resp = client.post("/api/v1/bank/statements", json={})
    assert resp.status_code in (401, 403)


def test_billing_plans_endpoint(client):
    resp = client.get("/api/v1/billing/plans", headers=AUTH)
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()["plans"]}
    assert {"free", "starter", "business"} <= codes


def test_billing_subscribe_free_for_default(client):
    # Default-DB API key uses the "default" pseudo-tenant; register it so billing
    # can attach a subscription, then subscribe to the free plan.
    from bizclinik_erp import tenancy
    tenancy.create_tenant("acme-bill", "Acme Billing", admin_password="pw")
    resp = client.post("/api/v1/billing/subscribe", headers=AUTH, json={
        "tenant_slug": "acme-bill", "plan_code": "free", "email": "a@b.com"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "active" and body["free"] is True

    status = client.get("/api/v1/billing/status?tenant_slug=acme-bill", headers=AUTH)
    assert status.status_code == 200
    assert status.json()["is_active"] is True


def test_billing_webhook_bad_signature_401(client):
    resp = client.post("/api/v1/billing/webhook/paystack",
                       content=b'{"event":"x"}',
                       headers={"x-paystack-signature": "bad"})
    assert resp.status_code == 401


def test_crm_lead_create_convert_and_pipeline(client):
    # Create a lead via API.
    r = client.post("/api/v1/crm/leads", headers=AUTH, json={
        "name": "Jane", "company": "Acme Ltd", "email": "j@acme.com"})
    assert r.status_code == 201, r.text
    lead_id = r.json()["id"]

    # It shows in the list.
    lst = client.get("/api/v1/crm/leads", headers=AUTH)
    assert any(l["id"] == lead_id for l in lst.json()["leads"])

    # Convert it (with a deal).
    conv = client.post(f"/api/v1/crm/leads/{lead_id}/convert"
                       "?create_deal=true&deal_amount=120000", headers=AUTH)
    assert conv.status_code == 200, conv.text
    assert conv.json()["customer_id"] and conv.json()["deal_id"]

    # Pipeline summary reflects the new (qualified) deal.
    pipe = client.get("/api/v1/crm/pipeline", headers=AUTH)
    assert pipe.status_code == 200
    assert pipe.json()["open_count"] >= 1


def test_crm_requires_key(client):
    assert client.get("/api/v1/crm/pipeline").status_code in (401, 403)


def test_customers_requires_key(client):
    resp = client.get("/api/v1/customers")  # no X-API-Key header
    assert resp.status_code in (401, 403)


def test_customers_with_key(client):
    _seed_customer_and_product()
    resp = client.get("/api/v1/customers", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert any(c["code"] == "CUST1" and c["name"] == "Acme Ltd" for c in body)


def test_create_invoice_and_fetch(client):
    _seed_customer_and_product()
    payload = {
        "customer_code": "CUST1",
        "invoice_date": date(2026, 1, 15).isoformat(),
        "due_date": date(2026, 2, 15).isoformat(),
        "lines": [
            {"sku": "SKU1", "qty": 3, "unit_price": 100.0, "tax_rate": 0.075},
        ],
    }
    resp = client.post("/api/v1/invoices", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["total"] == pytest.approx(322.5)  # 300 + 7.5% VAT
    number = created["number"]

    # GET list shows it.
    lst = client.get("/api/v1/invoices", headers=AUTH).json()
    assert any(i["number"] == number for i in lst)

    # GET detail shows the line.
    detail = client.get(f"/api/v1/invoices/{number}", headers=AUTH)
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["customer"] == "Acme Ltd"
    assert len(dbody["lines"]) == 1
    assert dbody["lines"][0]["sku"] == "SKU1"


def test_trial_balance_balanced(client):
    _seed_customer_and_product()
    # Post an invoice so the GL has activity to balance.
    payload = {
        "customer_code": "CUST1",
        "invoice_date": date(2026, 1, 15).isoformat(),
        "lines": [{"sku": "SKU1", "qty": 2, "unit_price": 50.0, "tax_rate": 0.075}],
    }
    assert client.post("/api/v1/invoices", json=payload, headers=AUTH).status_code == 201

    resp = client.get(
        "/api/v1/reports/trial-balance",
        params={"as_of": date(2026, 12, 31).isoformat()},
        headers=AUTH,
    )
    assert resp.status_code == 200
    tb = resp.json()
    assert tb["balanced"] is True
    assert tb["total_debit"] == pytest.approx(tb["total_credit"])
    assert tb["total_debit"] > 0
