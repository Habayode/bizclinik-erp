"""Tenant subscription & billing — built on the provider-agnostic payments layer.

Plans are defined in code (``PLANS``) with **placeholder NGN pricing you can
edit**. Subscriptions + charges live in the control plane (tenancy.py), so
billing state is shared across all tenant DBs and survives tenant data resets.

Flow:
  start_subscription(slug, plan, email)
      • free plan  -> activated immediately, no payment.
      • paid plan  -> create a pending charge + Subscription(pending), call the
                      configured payment provider's initialize(), return the
                      checkout URL + reference.
  confirm_by_reference(reference) / handle_webhook(provider, body, sig)
      • verify with the provider, mark the charge paid, and activate the
        subscription for one billing period.

The whole thing degrades gracefully before a provider is configured: free plans
still work; paid plans raise a clear "configure a provider" error.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from . import payments
from .. import authz
from .. import tenancy


# --------------------------------------------------------------------------- #
# Plans — EDIT THESE. price_ngn is per `interval`; 0 = free (no payment).      #
# --------------------------------------------------------------------------- #

# Features that require a plan to unlock. Anything NOT in this set is "core" and
# is available on every plan (sales, purchases, inventory, banking, payroll,
# tax, reports, GL, statements, settings, fixed assets, month-end).
GATED_FEATURES = frozenset({
    "bank_reconciliation", "firs_einvoice", "recurring",
    "multi_currency", "crm", "budgets", "api",
})


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price_ngn: float
    interval: str = "monthly"          # "monthly" | "yearly"
    features: list[str] = field(default_factory=list)   # marketing bullets
    max_users: Optional[int] = None     # None = unlimited
    unlocks: frozenset = frozenset()    # which GATED_FEATURES this plan grants

    @property
    def is_free(self) -> bool:
        return self.price_ngn <= 0

    @property
    def annual_price_ngn(self) -> float:
        """Annual price = 10 months (pay for 10, get 12 — 2 months free)."""
        return round(self.price_ngn * 10, 2)

    def price_for(self, interval: str) -> float:
        return self.annual_price_ngn if interval == "yearly" else self.price_ngn


ANNUAL_FREE_MONTHS = 2   # annual billing = monthly × (12 - this)

PLANS: dict[str, Plan] = {
    "free": Plan(
        "free", "Free", 0, "monthly",
        ["1 business", "Up to 2 users", "Core accounting"],
        max_users=2, unlocks=frozenset()),
    "starter": Plan(
        "starter", "Starter", 50000, "monthly",
        ["Up to 5 users", "Invoicing + bank rec", "Recurring",
         "FIRS e-invoice drafts"],
        max_users=5,
        unlocks=frozenset({"bank_reconciliation", "firs_einvoice", "recurring"})),
    "business": Plan(
        "business", "Business", 150000, "monthly",
        ["Unlimited users", "Multi-currency", "CRM", "Budgets",
         "API + webhooks", "Priority support"],
        max_users=None, unlocks=GATED_FEATURES),
}

_PERIOD_DAYS = {"monthly": 30, "yearly": 365}


def list_plans() -> list[dict]:
    return [{"code": p.code, "name": p.name, "price_ngn": p.price_ngn,
             "annual_price_ngn": p.annual_price_ngn,
             "interval": p.interval, "features": list(p.features),
             "is_free": p.is_free, "max_users": p.max_users,
             "unlocks": sorted(p.unlocks)} for p in PLANS.values()]


def get_plan(code: str) -> Optional[Plan]:
    return PLANS.get((code or "").strip().lower())


# --------------------------------------------------------------------------- #
# Entitlements — what a tenant's plan grants                                    #
# --------------------------------------------------------------------------- #

def effective_plan(tenant_slug: Optional[str]) -> Plan:
    """The plan whose entitlements apply right now.

    - No tenant (single-tenant / legacy default DB) -> Business (unrestricted),
      so non-SaaS installs are never gated.
    - Active subscription -> that plan.
    - No / lapsed subscription -> Free (graceful downgrade: core stays usable,
      premium features lock until they (re)subscribe).
    """
    if not tenant_slug:
        return PLANS["business"]
    sub = current_subscription(tenant_slug)
    if sub and sub["is_active"]:
        return get_plan(sub["plan_code"]) or PLANS["free"]
    return PLANS["free"]


def entitlements(tenant_slug: Optional[str]) -> dict:
    p = effective_plan(tenant_slug)
    return {"plan": p.code, "max_users": p.max_users,
            "unlocks": set(p.unlocks),
            "unrestricted": (not tenant_slug)}


def allows(tenant_slug: Optional[str], feature: str) -> bool:
    """True if ``feature`` is available to the tenant. Core features (anything
    not in GATED_FEATURES) are always allowed."""
    if feature not in GATED_FEATURES:
        return True
    return feature in effective_plan(tenant_slug).unlocks


def user_limit(tenant_slug: Optional[str]) -> Optional[int]:
    """Max user accounts for the tenant's plan; None = unlimited."""
    return effective_plan(tenant_slug).max_users


def can_add_user(tenant_slug: Optional[str], current_user_count: int) -> bool:
    lim = user_limit(tenant_slug)
    return lim is None or current_user_count < lim


# --------------------------------------------------------------------------- #
# Subscriptions                                                                #
# --------------------------------------------------------------------------- #

def _period_end(start: datetime, interval: str) -> datetime:
    return start + timedelta(days=_PERIOD_DAYS.get(interval, 30))


def _now() -> datetime:
    return datetime.utcnow()


def _gen_reference(slug: str) -> str:
    return f"BZK-{slug}-{secrets.token_hex(8)}"


def current_subscription(tenant_slug: str) -> Optional[dict]:
    from ..tenancy import Subscription
    fac = tenancy._control_factory()
    with fac() as s:
        sub = s.query(Subscription).filter_by(tenant_slug=tenant_slug).one_or_none()
        if not sub:
            return None
        active = (sub.status == "active" and sub.current_period_end is not None
                  and sub.current_period_end >= _now())
        return {
            "tenant_slug": sub.tenant_slug, "plan_code": sub.plan_code,
            "status": "active" if active else sub.status,
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "is_active": bool(active),
        }


def is_active(tenant_slug: str) -> bool:
    sub = current_subscription(tenant_slug)
    return bool(sub and sub["is_active"])


def _upsert_subscription(s, *, tenant_slug, plan_code, status,
                         period_start=None, period_end=None):
    from ..tenancy import Subscription
    sub = s.query(Subscription).filter_by(tenant_slug=tenant_slug).one_or_none()
    if not sub:
        sub = Subscription(tenant_slug=tenant_slug, plan_code=plan_code)
        s.add(sub)
    sub.plan_code = plan_code
    sub.status = status
    if period_start is not None:
        sub.current_period_start = period_start
    if period_end is not None:
        sub.current_period_end = period_end
    sub.updated_at = _now()
    return sub


def start_subscription(tenant_slug: str, plan_code: str, *, email: str,
                       interval: str = "monthly",
                       callback_url: Optional[str] = None,
                       provider_name: Optional[str] = None) -> dict:
    """Begin (or change) a subscription on a ``monthly`` or ``yearly`` cycle.

    Annual billing charges 10× the monthly price (2 months free) and runs for a
    365-day period. Free plan -> activated immediately. Paid plan -> a pending
    charge is created for the chosen cycle's amount and the payment provider is
    asked to initialise a checkout; the returned dict carries
    ``authorization_url`` and ``reference``. Raises ValueError on unknown
    tenant/plan/interval, and RuntimeError if a paid plan is requested with no
    provider configured.
    """
    authz.require_perm("manage.settings")
    if not tenancy.get_tenant(tenant_slug):
        raise ValueError(f"Unknown tenant '{tenant_slug}'.")
    plan = get_plan(plan_code)
    if not plan:
        raise ValueError(f"Unknown plan '{plan_code}'.")
    interval = (interval or "monthly").lower()
    if interval not in _PERIOD_DAYS:
        raise ValueError(f"Unknown billing interval '{interval}'.")

    from ..tenancy import BillingCharge
    fac = tenancy._control_factory()

    if plan.is_free:
        with fac() as s:
            start = _now()
            _upsert_subscription(s, tenant_slug=tenant_slug, plan_code=plan.code,
                                 status="active", period_start=start,
                                 period_end=_period_end(start, interval))
            s.commit()
        return {"plan": plan.code, "status": "active", "free": True,
                "interval": interval, "amount_ngn": 0.0,
                "authorization_url": None, "reference": None}

    amount = plan.price_for(interval)
    provider = payments.get_provider(provider_name)
    if not provider.configured():
        raise RuntimeError(
            "No payment provider configured. Set PAYMENTS_PROVIDER and its "
            "API key to subscribe to a paid plan.")

    reference = _gen_reference(tenant_slug)
    init = provider.initialize(amount_ngn=amount, email=email,
                               reference=reference, callback_url=callback_url)
    with fac() as s:
        s.add(BillingCharge(reference=init.reference or reference,
                            tenant_slug=tenant_slug, plan_code=plan.code,
                            amount_ngn=amount, provider=provider.name,
                            status="pending"))
        _upsert_subscription(s, tenant_slug=tenant_slug, plan_code=plan.code,
                             status="pending")
        s.commit()
    return {"plan": plan.code, "status": "pending", "free": False,
            "interval": interval, "amount_ngn": amount,
            "authorization_url": init.authorization_url,
            "reference": init.reference or reference, "provider": provider.name}


def confirm_by_reference(reference: str, *, provider_name: Optional[str] = None) -> dict:
    """Verify a charge with the provider; on success activate the subscription."""
    from ..tenancy import BillingCharge
    fac = tenancy._control_factory()
    with fac() as s:
        charge = s.query(BillingCharge).filter_by(reference=reference).one_or_none()
        if not charge:
            raise ValueError(f"No charge for reference {reference!r}.")
        if charge.status == "paid":
            return {"reference": reference, "status": "already_paid",
                    "tenant_slug": charge.tenant_slug, "activated": False}
        prov = payments.get_provider(provider_name or charge.provider)
        status = prov.verify(reference)
        if status.status != "success":
            return {"reference": reference, "status": status.status,
                    "tenant_slug": charge.tenant_slug, "activated": False}
        plan = get_plan(charge.plan_code) or PLANS["free"]
        # The cycle is recoverable from the amount charged: annual = monthly×10,
        # so a charge at (or above) the annual price means a 365-day period.
        interval = ("yearly" if charge.amount_ngn >= plan.annual_price_ngn - 0.5
                    else "monthly")
        start = _now()
        # Atomically claim the charge (pending -> paid). On a concurrent webhook
        # replay only one caller flips the row; the loser updates 0 rows and
        # does not re-activate the subscription.
        claimed = s.query(BillingCharge).filter(
            BillingCharge.reference == reference,
            BillingCharge.status == "pending",
        ).update({"status": "paid", "paid_at": start},
                 synchronize_session=False)
        if not claimed:
            s.commit()
            return {"reference": reference, "status": "already_paid",
                    "tenant_slug": charge.tenant_slug, "activated": False}
        _upsert_subscription(s, tenant_slug=charge.tenant_slug,
                             plan_code=charge.plan_code, status="active",
                             period_start=start,
                             period_end=_period_end(start, interval))
        s.commit()
        return {"reference": reference, "status": "success",
                "tenant_slug": charge.tenant_slug, "activated": True,
                "plan_code": charge.plan_code, "interval": interval}


def _extract_reference(body: bytes) -> Optional[str]:
    try:
        d = json.loads(body.decode("utf-8") or "{}")
    except Exception:
        return None
    data = d.get("data", d) if isinstance(d, dict) else {}
    for key in ("reference", "tx_ref", "txRef", "transaction_reference"):
        v = (data or {}).get(key) or (d.get(key) if isinstance(d, dict) else None)
        if v:
            return str(v)
    return None


def handle_webhook(provider_name: str, body: bytes, signature: str) -> dict:
    """Verify a provider webhook and confirm the referenced charge.

    Returns a small status dict; never raises on a bad signature (returns
    ``{"verified": False}``) so the caller can answer 200/401 cleanly.
    """
    prov = payments.get_provider(provider_name)
    if not prov.verify_webhook(body, signature or ""):
        return {"verified": False}
    reference = _extract_reference(body)
    if not reference:
        return {"verified": True, "handled": False, "reason": "no reference in payload"}
    result = confirm_by_reference(reference, provider_name=provider_name)
    return {"verified": True, "handled": True, **result}
