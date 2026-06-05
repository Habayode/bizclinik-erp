"""Provider-agnostic payments layer.

One interface, swappable backends — Paystack, Flutterwave, or Moniepoint —
chosen at runtime by the ``PAYMENTS_PROVIDER`` environment variable. Switching
processors (or adding a new one) is a config change, not a code change: the
rest of the app only ever talks to ``get_provider()`` and the small
``PaymentInit`` / ``PaymentStatus`` result objects.

    PAYMENTS_PROVIDER = paystack | flutterwave | moniepoint | null   (default: null)

Per-provider credentials (set only the one you use):
    Paystack     PAYSTACK_SECRET_KEY
    Flutterwave  FLUTTERWAVE_SECRET_KEY, FLUTTERWAVE_WEBHOOK_HASH
    Moniepoint   MONIEPOINT_SECRET_KEY  (HMAC-SHA512 webhook signing)

HTTP uses the stdlib (no extra dependency). All network calls go through
``_http_json`` so tests can stub them; webhook-signature verification is pure
and unit-tested. With no provider configured the layer is a safe no-op
(``NullProvider``) so the app boots fine before billing is switched on.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------- #
# Result objects                                                               #
# --------------------------------------------------------------------------- #

@dataclass
class PaymentInit:
    provider: str
    reference: str
    authorization_url: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class PaymentStatus:
    provider: str
    reference: str
    status: str                      # "success" | "pending" | "failed" | "unknown"
    amount: float = 0.0              # NGN
    raw: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# HTTP helper (stub-able)                                                      #
# --------------------------------------------------------------------------- #

def _http_json(method: str, url: str, *, headers: dict, body: Optional[dict] = None,
               timeout: int = 30) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted hosts)
        return json.loads(resp.read().decode("utf-8") or "{}")


# --------------------------------------------------------------------------- #
# Providers                                                                    #
# --------------------------------------------------------------------------- #

class PaymentProvider:
    """Base interface. Subclasses implement initialize/verify/verify_webhook."""

    name = "base"

    def configured(self) -> bool:
        return False

    def initialize(self, *, amount_ngn: float, email: str, reference: str,
                   callback_url: Optional[str] = None) -> PaymentInit:
        raise NotImplementedError

    def verify(self, reference: str) -> PaymentStatus:
        raise NotImplementedError

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        raise NotImplementedError


class NullProvider(PaymentProvider):
    """Used when no provider is configured. Never makes network calls."""
    name = "null"

    def configured(self) -> bool:
        return False

    def initialize(self, **_) -> PaymentInit:
        raise RuntimeError(
            "No payment provider configured. Set PAYMENTS_PROVIDER and its keys.")

    def verify(self, reference: str) -> PaymentStatus:
        return PaymentStatus(self.name, reference, "unknown")

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        return False


class PaystackProvider(PaymentProvider):
    name = "paystack"
    BASE = "https://api.paystack.co"

    def __init__(self) -> None:
        self.secret = os.environ.get("PAYSTACK_SECRET_KEY", "").strip()

    def configured(self) -> bool:
        return bool(self.secret)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.secret}",
                "Content-Type": "application/json"}

    def initialize(self, *, amount_ngn: float, email: str, reference: str,
                   callback_url: Optional[str] = None) -> PaymentInit:
        body = {"email": email, "amount": int(round(amount_ngn * 100)),  # kobo
                "reference": reference, "currency": "NGN"}
        if callback_url:
            body["callback_url"] = callback_url
        r = _http_json("POST", f"{self.BASE}/transaction/initialize",
                       headers=self._headers(), body=body)
        d = r.get("data", {})
        return PaymentInit(self.name, d.get("reference", reference),
                           d.get("authorization_url"), r)

    def verify(self, reference: str) -> PaymentStatus:
        r = _http_json("GET", f"{self.BASE}/transaction/verify/{reference}",
                       headers=self._headers())
        d = r.get("data", {})
        st = "success" if d.get("status") == "success" else (
            "failed" if d.get("status") in ("failed", "abandoned") else "pending")
        return PaymentStatus(self.name, reference, st,
                             round((d.get("amount") or 0) / 100.0, 2), r)

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        if not (self.secret and signature):
            return False
        digest = hmac.new(self.secret.encode(), body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(digest, signature)


class FlutterwaveProvider(PaymentProvider):
    name = "flutterwave"
    BASE = "https://api.flutterwave.com/v3"

    def __init__(self) -> None:
        self.secret = os.environ.get("FLUTTERWAVE_SECRET_KEY", "").strip()
        self.webhook_hash = os.environ.get("FLUTTERWAVE_WEBHOOK_HASH", "").strip()

    def configured(self) -> bool:
        return bool(self.secret)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.secret}",
                "Content-Type": "application/json"}

    def initialize(self, *, amount_ngn: float, email: str, reference: str,
                   callback_url: Optional[str] = None) -> PaymentInit:
        body = {"tx_ref": reference, "amount": round(amount_ngn, 2),
                "currency": "NGN", "customer": {"email": email}}
        if callback_url:
            body["redirect_url"] = callback_url
        r = _http_json("POST", f"{self.BASE}/payments",
                       headers=self._headers(), body=body)
        link = (r.get("data") or {}).get("link")
        return PaymentInit(self.name, reference, link, r)

    def verify(self, reference: str) -> PaymentStatus:
        # Flutterwave verifies by tx_ref.
        r = _http_json("GET",
                       f"{self.BASE}/transactions/verify_by_reference?tx_ref={reference}",
                       headers=self._headers())
        d = r.get("data", {})
        st = "success" if d.get("status") == "successful" else (
            "failed" if d.get("status") == "failed" else "pending")
        return PaymentStatus(self.name, reference, st,
                             round(float(d.get("amount") or 0), 2), r)

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        # Flutterwave sends a static 'verif-hash' header equal to your secret hash.
        if not (self.webhook_hash and signature):
            return False
        return hmac.compare_digest(self.webhook_hash, signature)


class MoniepointProvider(PaymentProvider):
    name = "moniepoint"
    BASE = os.environ.get("MONIEPOINT_BASE", "https://api.moniepoint.com")

    def __init__(self) -> None:
        self.secret = os.environ.get("MONIEPOINT_SECRET_KEY", "").strip()

    def configured(self) -> bool:
        return bool(self.secret)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.secret}",
                "Content-Type": "application/json"}

    def initialize(self, *, amount_ngn: float, email: str, reference: str,
                   callback_url: Optional[str] = None) -> PaymentInit:
        body = {"amount": round(amount_ngn, 2), "currency": "NGN",
                "reference": reference, "customer": {"email": email}}
        if callback_url:
            body["redirectUrl"] = callback_url
        r = _http_json("POST", f"{self.BASE}/v1/payments/init",
                       headers=self._headers(), body=body)
        d = r.get("data", r)
        return PaymentInit(self.name, d.get("reference", reference),
                           d.get("checkoutUrl") or d.get("authorization_url"), r)

    def verify(self, reference: str) -> PaymentStatus:
        r = _http_json("GET", f"{self.BASE}/v1/payments/{reference}",
                       headers=self._headers())
        d = r.get("data", r)
        raw_status = str(d.get("status", "")).lower()
        st = "success" if raw_status in ("success", "successful", "paid") else (
            "failed" if raw_status in ("failed", "declined") else "pending")
        return PaymentStatus(self.name, reference, st,
                             round(float(d.get("amount") or 0), 2), r)

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        if not (self.secret and signature):
            return False
        digest = hmac.new(self.secret.encode(), body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(digest, signature)


_PROVIDERS = {
    "paystack": PaystackProvider,
    "flutterwave": FlutterwaveProvider,
    "moniepoint": MoniepointProvider,
    "null": NullProvider,
}


def get_provider(name: Optional[str] = None) -> PaymentProvider:
    """Return the configured payment provider.

    ``name`` overrides the ``PAYMENTS_PROVIDER`` env var (handy for tests). An
    unknown/unset name falls back to NullProvider, so callers can always import
    and call this without crashing before billing is configured.
    """
    key = (name or os.environ.get("PAYMENTS_PROVIDER") or "null").strip().lower()
    return _PROVIDERS.get(key, NullProvider)()


def available_providers() -> list[str]:
    return [k for k in _PROVIDERS if k != "null"]
