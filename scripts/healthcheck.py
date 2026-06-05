"""Probe the Streamlit `_stcore/health` endpoint.

Usage:
    python scripts/healthcheck.py https://erp.hagai.online

Exit code 0 if HTTP 200 and the body contains "ok", non-zero otherwise.
Designed to be used as a cron / uptime probe (e.g. UptimeRobot, Task
Scheduler) -- the exit code is the signal.
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urljoin

try:
    import requests
except ImportError:  # pragma: no cover -- only hit if requests missing
    print("requests is required: pip install requests", file=sys.stderr)
    raise SystemExit(2)


HEALTH_PATH = "/_stcore/health"
DEFAULT_TIMEOUT = 10


def check(base_url: str, *, timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, str]:
    """Return (ok, detail) for the health endpoint at ``base_url``."""
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url
    if not base_url.endswith("/"):
        base_url = base_url + "/"
    url = urljoin(base_url, HEALTH_PATH.lstrip("/"))
    try:
        r = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return False, f"request failed: {exc}"
    body = (r.text or "").strip()
    if r.status_code == 200 and "ok" in body.lower():
        return True, f"200 {body!r}"
    return False, f"status={r.status_code} body={body!r}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="healthcheck",
        description="Probe Streamlit /_stcore/health. Exit 0 on healthy.",
    )
    parser.add_argument("url", help="Base URL, e.g. https://erp.hagai.online")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress stdout on success.",
    )
    args = parser.parse_args(argv)

    ok, detail = check(args.url, timeout=args.timeout)
    if ok:
        if not args.quiet:
            print(f"OK {args.url} -> {detail}")
        return 0
    print(f"FAIL {args.url} -> {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
