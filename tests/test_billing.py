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
    assert billing.get_plan("starter").price_ngn == 50000
    assert billing.get_plan("business").price_ngn == 150000
    assert billing.get_plan("free").is_free


def test_annual_pricing_is_two_months_free():
    from bizclinik_erp.services import billing
    starter = billing.get_plan("starter")
    business = billing.get_plan("business")
    # Annual = monthly × 10 (pay for 10, get 12).
    assert starter.annual_price_ngn == 500_000
    assert business.annual_price_ngn == 1_500_000
    assert starter.price_for("yearly") == 500_000
    assert starter.price_for("monthly") == 50_000
    assert billing.get_plan("free").annual_price_ngn == 0
    # Saving equals two monthly payments.
    assert business.price_ngn * 12 - business.annual_price_ngn == business.price_ngn * 2
    assert {"annual_price_ngn"} <= billing.list_plans()[1].keys()


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
    assert conf["interval"] == "monthly"
    assert billing.is_active("acme") is True
    sub = billing.current_subscription("acme")
    assert sub["plan_code"] == "starter"
    # Monthly cycle -> ~30-day period.
    days = (sub["current_period_end"] - sub["current_period_start"]).days
    assert 29 <= days <= 31


def test_confirm_is_idempotent_on_replay(control_env, monkeypatch):
    from bizclinik_erp.services import billing, payments
    monkeypatch.setattr(payments, "get_provider", lambda name=None: FakeProvider())
    res = billing.start_subscription("acme", "starter", email="a@b.com")
    c1 = billing.confirm_by_reference(res["reference"])
    assert c1["activated"] is True
    c2 = billing.confirm_by_reference(res["reference"])   # webhook/replay
    assert c2["activated"] is False and c2["status"] == "already_paid"
    sub = billing.current_subscription("acme")
    assert sub and sub["status"] == "active"


def test_annual_checkout_charges_10x_and_runs_a_year(control_env, monkeypatch):
    from bizclinik_erp.services import billing, payments
    monkeypatch.setattr(payments, "get_provider", lambda name=None: FakeProvider())

    res = billing.start_subscription("acme", "business", email="a@b.com",
                                     interval="yearly")
    assert res["status"] == "pending"
    assert res["interval"] == "yearly"
    assert res["amount_ngn"] == 1_500_000          # 150k × 10

    conf = billing.confirm_by_reference(res["reference"])
    assert conf["activated"] is True
    assert conf["interval"] == "yearly"             # recovered from the amount
    sub = billing.current_subscription("acme")
    days = (sub["current_period_end"] - sub["current_period_start"]).days
    assert days >= 360                              # ~365-day period


def test_unknown_interval_rejected(control_env):
    from bizclinik_erp.services import billing
    with pytest.raises(ValueError, match="interval"):
        billing.start_subscription("acme", "starter", email="a@b.com",
                                   interval="weekly")


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


# --------------------------------------------------------------------------- #
# Entitlements / feature gating                                                #
# --------------------------------------------------------------------------- #

def test_plan_unlocks_definition():
    from bizclinik_erp.services import billing
    # Free unlocks nothing gated; Starter unlocks the 3 starter features;
    # Business unlocks everything.
    assert billing.PLANS["free"].unlocks == frozenset()
    assert billing.PLANS["starter"].unlocks == frozenset(
        {"bank_reconciliation", "firs_einvoice", "recurring"})
    assert billing.PLANS["business"].unlocks == billing.GATED_FEATURES
    # max_users
    assert billing.PLANS["free"].max_users == 2
    assert billing.PLANS["starter"].max_users == 5
    assert billing.PLANS["business"].max_users is None


def test_allows_core_features_always():
    from bizclinik_erp.services import billing
    # A non-gated (core) feature is allowed regardless of plan/tenant.
    assert billing.allows("anytenant", "sales") is True
    assert billing.allows(None, "reports") is True


def test_effective_plan_no_tenant_is_unrestricted():
    from bizclinik_erp.services import billing
    # Single-tenant / legacy default DB -> Business (nothing gated).
    p = billing.effective_plan(None)
    assert p.code == "business"
    for feat in billing.GATED_FEATURES:
        assert billing.allows(None, feat) is True


def test_no_subscription_downgrades_to_free(control_env):
    from bizclinik_erp.services import billing
    # acme exists but has no subscription -> Free entitlements.
    assert billing.effective_plan("acme").code == "free"
    assert billing.allows("acme", "crm") is False
    assert billing.allows("acme", "bank_reconciliation") is False
    assert billing.user_limit("acme") == 2


def test_starter_unlocks_starter_features_only(control_env, monkeypatch):
    from bizclinik_erp.services import billing, payments
    monkeypatch.setattr(payments, "get_provider", lambda name=None: FakeProvider())
    res = billing.start_subscription("acme", "starter", email="a@b.com")
    billing.confirm_by_reference(res["reference"])
    assert billing.effective_plan("acme").code == "starter"
    # Starter features on:
    for feat in ("bank_reconciliation", "firs_einvoice", "recurring"):
        assert billing.allows("acme", feat) is True
    # Business-only features still locked:
    for feat in ("crm", "multi_currency", "budgets", "api"):
        assert billing.allows("acme", feat) is False
    assert billing.user_limit("acme") == 5


def test_business_unlocks_everything(control_env, monkeypatch):
    from bizclinik_erp.services import billing, payments
    monkeypatch.setattr(payments, "get_provider", lambda name=None: FakeProvider())
    res = billing.start_subscription("acme", "business", email="a@b.com")
    billing.confirm_by_reference(res["reference"])
    assert billing.effective_plan("acme").code == "business"
    for feat in billing.GATED_FEATURES:
        assert billing.allows("acme", feat) is True
    assert billing.user_limit("acme") is None
    assert billing.can_add_user("acme", 999) is True


def test_can_add_user_respects_limit(control_env):
    from bizclinik_erp.services import billing
    # No sub -> Free -> max 2 users.
    assert billing.can_add_user("acme", 0) is True
    assert billing.can_add_user("acme", 1) is True
    assert billing.can_add_user("acme", 2) is False
    assert billing.can_add_user("acme", 5) is False


def test_lapsed_subscription_downgrades_to_free(control_env, monkeypatch):
    from bizclinik_erp.services import billing, payments
    from bizclinik_erp import tenancy
    monkeypatch.setattr(payments, "get_provider", lambda name=None: FakeProvider())
    res = billing.start_subscription("acme", "business", email="a@b.com")
    billing.confirm_by_reference(res["reference"])
    assert billing.allows("acme", "crm") is True
    # Force the period to have ended.
    from bizclinik_erp.tenancy import Subscription
    from datetime import datetime, timedelta
    fac = tenancy._control_factory()
    with fac() as s:
        sub = s.query(Subscription).filter_by(tenant_slug="acme").one()
        sub.current_period_end = datetime.utcnow() - timedelta(days=1)
        s.commit()
    # Lapsed -> Free -> premium locks again.
    assert billing.effective_plan("acme").code == "free"
    assert billing.allows("acme", "crm") is False
