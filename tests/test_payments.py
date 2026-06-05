"""Fluid payments layer: provider selection, webhook signatures, init (stubbed)."""
from __future__ import annotations

import hashlib
import hmac

import pytest


def test_provider_selection(monkeypatch):
    from bizclinik_erp.services import payments
    assert payments.get_provider("paystack").name == "paystack"
    assert payments.get_provider("flutterwave").name == "flutterwave"
    assert payments.get_provider("moniepoint").name == "moniepoint"
    # Unknown / unset -> safe Null provider.
    monkeypatch.delenv("PAYMENTS_PROVIDER", raising=False)
    assert payments.get_provider().name == "null"
    assert payments.get_provider("nope").name == "null"


def test_null_provider_is_safe():
    from bizclinik_erp.services import payments
    p = payments.get_provider("null")
    assert p.configured() is False
    assert p.verify("ref1").status == "unknown"
    assert p.verify_webhook(b"{}", "sig") is False
    with pytest.raises(RuntimeError):
        p.initialize(amount_ngn=100, email="a@b.com", reference="r")


def test_paystack_webhook_signature(monkeypatch):
    from bizclinik_erp.services import payments
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_secret")
    p = payments.get_provider("paystack")
    body = b'{"event":"charge.success"}'
    good = hmac.new(b"sk_test_secret", body, hashlib.sha512).hexdigest()
    assert p.verify_webhook(body, good) is True
    assert p.verify_webhook(body, "deadbeef") is False
    assert p.verify_webhook(body, "") is False


def test_flutterwave_webhook_hash(monkeypatch):
    from bizclinik_erp.services import payments
    monkeypatch.setenv("FLUTTERWAVE_SECRET_KEY", "FLWSECK_test")
    monkeypatch.setenv("FLUTTERWAVE_WEBHOOK_HASH", "myhash123")
    p = payments.get_provider("flutterwave")
    assert p.verify_webhook(b"{}", "myhash123") is True
    assert p.verify_webhook(b"{}", "wrong") is False


def test_moniepoint_webhook_signature(monkeypatch):
    from bizclinik_erp.services import payments
    monkeypatch.setenv("MONIEPOINT_SECRET_KEY", "msk_secret")
    p = payments.get_provider("moniepoint")
    body = b'{"status":"success"}'
    good = hmac.new(b"msk_secret", body, hashlib.sha512).hexdigest()
    assert p.verify_webhook(body, good) is True
    assert p.verify_webhook(body, "x") is False


def test_paystack_initialize_stubbed(monkeypatch):
    from bizclinik_erp.services import payments
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test")
    captured = {}

    def fake_http(method, url, *, headers, body=None, timeout=30):
        captured["url"] = url
        captured["body"] = body
        return {"status": True, "data": {
            "reference": body["reference"],
            "authorization_url": "https://checkout.paystack.com/abc123"}}

    monkeypatch.setattr(payments, "_http_json", fake_http)
    p = payments.get_provider("paystack")
    res = p.initialize(amount_ngn=1500.0, email="a@b.com", reference="ref-xyz",
                       callback_url="https://erp.example/cb")
    assert res.provider == "paystack"
    assert res.authorization_url.endswith("abc123")
    # NGN converted to kobo.
    assert captured["body"]["amount"] == 150000
    assert captured["body"]["reference"] == "ref-xyz"


def test_flutterwave_verify_stubbed(monkeypatch):
    from bizclinik_erp.services import payments
    monkeypatch.setenv("FLUTTERWAVE_SECRET_KEY", "FLWSECK")
    monkeypatch.setattr(payments, "_http_json",
                        lambda *a, **k: {"data": {"status": "successful", "amount": 2500}})
    st = payments.get_provider("flutterwave").verify("tx-1")
    assert st.status == "success"
    assert st.amount == 2500.0
