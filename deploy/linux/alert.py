#!/usr/bin/env python3
"""OnFailure handler: notify the operator that a Trakit365 systemd unit failed.

Invoked by bizclinik-alert@<unit>.service. Sends via the app's notifications
transport (Resend HTTP API) because the DigitalOcean droplet blocks outbound
SMTP, so SMTP alerts would silently never arrive. Reads ALERT_EMAIL (falls back
to DEMO_REQUEST_EMAIL) and the app env (RESEND_API_KEY / RESEND_FROM)."""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, "/opt/bizclinik-erp")


def main() -> int:
    unit = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    to = os.environ.get("ALERT_EMAIL") or os.environ.get("DEMO_REQUEST_EMAIL", "")
    if not to:
        return 0
    try:
        from bizclinik_erp.services import notifications
    except Exception:
        return 0
    if not notifications.email_configured():
        return 0
    try:
        log = subprocess.run(
            ["journalctl", "-u", unit, "-n", "20", "--no-pager"],
            capture_output=True, text=True, timeout=15).stdout
    except Exception:
        log = "(journal unavailable)"
    body = f"A Trakit365 systemd unit failed: {unit}\n\nRecent log:\n{log}"
    try:
        notifications.send_message(
            to_addr=to, subject=f"[Trakit365] unit failed: {unit}", body_text=body)
    except Exception as exc:
        print("alert send failed:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
