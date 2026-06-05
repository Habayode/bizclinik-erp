"""Optional error tracking via Sentry.

Zero-config and dormant by default: ``init_sentry()`` is a no-op unless the
``SENTRY_DSN`` environment variable is set AND the ``sentry-sdk`` package is
installed. This lets us ship the wiring now and turn it on later by just
setting a DSN on the server — no code change, no hard dependency.
"""
from __future__ import annotations

import os

_initialised = False


def init_sentry(component: str = "app") -> bool:
    """Initialise Sentry if SENTRY_DSN is set and sentry-sdk is importable.

    Returns True if Sentry was initialised, False otherwise. Safe to call more
    than once (subsequent calls are no-ops).
    """
    global _initialised
    if _initialised:
        return True

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk  # noqa: PLC0415 -- optional dependency
    except Exception:
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            release=os.environ.get("BIZCLINIK_RELEASE"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0") or "0"),
            send_default_pii=False,
        )
        sentry_sdk.set_tag("component", component)
        _initialised = True
        return True
    except Exception:
        return False
