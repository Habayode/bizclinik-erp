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


def test_health_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


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
