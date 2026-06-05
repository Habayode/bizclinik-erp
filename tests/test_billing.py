"""Subscription/billing layer over the payments abstraction."""
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


class FakeProvider:
    name = "fake"

    def configured(self):
        return True

    def initialize(self, *, amount_ngn, email, reference, callback_url=None):
        from bizclinik_erp.services import payments
        return payments.PaymentInit("fake", reference,
                                    f"https://pay.example/{reference}", {})

    def verify(self, reference):
        from bizclinik_erp.services import payments
        return payments.PaymentStatus("fake", reference, "success", 15000.0, {})

    def verify_webhook(self, body, signature):
        return signature == "valid"


def test_plans_registry():
    from bizclinik_erp.services import billing
    codes = {p["code"] for p in billing.list_plans()}
    assert {"free", "starter", "business"} <= codes
    assert billing.get_plan("starter").price_ngn == 15000
    assert billing.get_plan("free").is_free


def test_free_plan_activates_immediately(control_env):
    from bizclinik_erp.services import billing
    res = billing.start_subscription("acme", "free", email="a@b.com")
    assert res["status"] == "active" and res["free"] is True
    assert billing.is_active("acme") is True
    sub = billing.current_subscription("acme")
    assert sub["plan_code"] == "free" and sub["is_active"]


def test_paid_plan_without_provider_raises(control_env, monkeypatch):
    from bizclinik_erp.services import billing, payments
    monkeypatch.delenv("PAYMENTS_PROVIDER", raising=False)
    monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
    monkeypatch.delenv("FLUTTERWAVE_SECRET_KEY", raising=False)
    monkeypatch.delenv("MONIEPOINT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        billing.start_subscription("acme", "business", email="a@b.com")


def test_paid_plan_checkout_then_confirm(control_env, monkeypatch):
    from bizclinik_erp.services import billing, payments
    monkeypatch.setattr(payments, "get_provider", lambda name=None: FakeProvider())

    res = billing.start_subscription("acme", "starter", email="a@b.com",
                                     callback_url="https://erp/cb")
    assert res["status"] == "pending"
    assert res["authorization_url"].endswith(res["reference"])
    assert billing.is_active("acme") is False     # not active until paid

    conf = billing.confirm_by_reference(res["reference"])
    assert conf["activated"] is True
    assert billing.is_active("acme") is True
    assert billing.current_subscription("acme")["plan_code"] == "starter"


def test_webhook_activates_on_valid_signature(control_env, monkeypatch):
    import json
    from bizclinik_erp.services import billing, payments
    monkeypatch.setattr(payments, "get_provider", lambda name=None: FakeProvider())

    res = billing.start_subscription("acme", "business", email="a@b.com")
    ref = res["reference"]
    body = json.dumps({"event": "charge.success",
                       "data": {"reference": ref}}).encode()

    # Bad signature -> not verified, no activation.
    assert billing.handle_webhook("fake", body, "nope")["verified"] is False
    assert billing.is_active("acme") is False

    # Valid signature -> verified + activated.
    out = billing.handle_webhook("fake", body, "valid")
    assert out["verified"] and out["handled"] and out["activated"]
    assert billing.is_active("acme") is True
