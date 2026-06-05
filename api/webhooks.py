"""Outbound webhook dispatch.

Best-effort fire-and-forget POSTs to every URL configured in the env var
``BIZCLINIK_WEBHOOK_URLS`` (comma-separated). Failures never propagate — a
down or slow subscriber must not break the API request that triggered the
event. Errors are logged to stdout only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

# Short timeout so a hanging subscriber can't stall the request thread.
_TIMEOUT_SECONDS = 4


def _webhook_urls() -> list[str]:
    raw = os.environ.get("BIZCLINIK_WEBHOOK_URLS", "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def fire(event: str, payload: dict) -> None:
    """POST ``{event, sent_at, data}`` to every configured webhook URL.

    Best-effort: short timeout, all exceptions swallowed and logged to stdout.
    Does nothing (silently) when no URLs are configured.
    """
    urls = _webhook_urls()
    if not urls:
        return
    body: dict[str, Any] = {
        "event": event,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    for url in urls:
        try:
            resp = requests.post(url, json=body, timeout=_TIMEOUT_SECONDS)
            print(f"[webhook] {event} -> {url} : {resp.status_code}")
        except Exception as exc:  # noqa: BLE001 — deliberately swallow everything
            print(f"[webhook] {event} -> {url} : FAILED ({exc!r})")


def emit_invoice_created(invoice_dict: dict) -> None:
    """Convenience wrapper firing the ``invoice.created`` event."""
    fire("invoice.created", invoice_dict)
