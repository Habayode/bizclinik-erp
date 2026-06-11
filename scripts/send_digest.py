"""Build today's notification digest and email it (or print it).

Usage:
    python scripts/send_digest.py --to someone@example.com
    python scripts/send_digest.py --to ops@firm.com --as-of 2026-06-05

Reads BIZCLINIK_DB_PATH via get_settings (same DB the app uses). If SMTP is
not configured (SMTP_HOST unset) the digest is printed to stdout instead of
sent — handy when wiring this up under a cron / systemd timer before SMTP
credentials are in place.

Exit code 0 when the digest is built (sent or printed); non-zero on error.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Allow running as a bare script: add the repo root to sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bizclinik_erp.db import get_session
from bizclinik_erp.services import notifications


def _parse_as_of(value: str | None) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="send_digest",
        description="Build and send (or print) the Trakit365 ERP daily digest.",
    )
    parser.add_argument("--to", required=True, help="Recipient email address.")
    parser.add_argument(
        "--as-of", default=None,
        help="ISO date for the digest (default: today).",
    )
    args = parser.parse_args(argv)

    try:
        as_of = _parse_as_of(args.as_of)
    except ValueError:
        print(f"Invalid --as-of date: {args.as_of!r} (expected YYYY-MM-DD).",
              file=sys.stderr)
        return 2

    with get_session() as s:
        digest = notifications.build_digest(s, as_of=as_of)

    sent = notifications.send_digest_email(digest, to_addr=args.to)
    if sent:
        print(f"Digest sent to {args.to} (as of {digest['as_of']}).")
        return 0

    # SMTP not configured (or send failed) — print the digest so nothing is lost.
    print("SMTP not configured (set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/"
          "SMTP_FROM) — printing digest instead:\n", file=sys.stderr)
    print(notifications.render_digest_text(digest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
