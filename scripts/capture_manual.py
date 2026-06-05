"""Capture user-manual screenshots from the local Streamlit app via Playwright.

Assumes the app is running on http://localhost:8501 against the GreenLeaf demo DB
(see scripts/demo_seed.py). Logs in, visits each page, and saves PNGs into
docs/manual_images/.

    python scripts/capture_manual.py
"""
from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501"
USER, PW = "admin", "GreenLeaf#2026"
OUT = Path(__file__).resolve().parent.parent / "docs" / "manual_images"
OUT.mkdir(parents=True, exist_ok=True)

# (filename, sidebar-link-text, settle-seconds) — navigate by CLICK to keep the
# Streamlit session (full-page navigation logs you out).
PAGES = [
    ("02_sales", "Sales", 4),
    ("03_purchases", "Purchases", 4),
    ("04_inventory", "Inventory", 4),
    ("05_banking", "Banking", 4),
    ("06_bank_reconciliation", "Bank Reconciliation", 4),
    ("07_payroll", "Payroll", 4),
    ("08_fixed_assets", "Fixed Assets", 4),
    ("09_general_ledger", "General Ledger", 5),
    ("10_statements", "Statements", 5),
    ("11_month_end", "Month End", 4),
    ("12_budgets", "Budgets", 4),
    ("13_currencies", "Currencies", 4),
    ("14_firs_einvoice", "FIRS Einvoice", 4),
    ("15_crm", "CRM", 4),
    ("16_settings", "Settings", 4),
    ("17_tenants", "Tenants", 4),
    ("18_billing", "Billing", 4),
    ("19_reports", "Reports", 5),
    ("20_recurring", "Recurring", 4),
]


def run() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000},
                                  device_scale_factor=1)
        page = ctx.new_page()

        # ---- login ----
        page.goto(BASE, wait_until="domcontentloaded")
        time.sleep(6)
        try:
            page.fill('input[aria-label="Username"]', USER, timeout=15000)
            page.fill('input[aria-label="Password"]', PW, timeout=15000)
            page.get_by_role("button", name="Sign in").first.click()
            time.sleep(6)
            print("logged in")
        except Exception as e:
            print("login step:", e)

        # ---- expand the collapsed sidebar nav ("View N more") ----
        import re as _re
        for attempt in range(3):
            try:
                page.locator('[data-testid="stSidebarNav"]').get_by_text(
                    _re.compile(r"View .*more", _re.I)).first.click(timeout=4000)
                time.sleep(1.0)
                break
            except Exception:
                try:
                    page.get_by_text(_re.compile(r"View .*more", _re.I)).first.click(timeout=4000)
                    time.sleep(1.0); break
                except Exception:
                    time.sleep(1.0)
        nlinks = page.locator('[data-testid="stSidebarNav"] a').count()
        print("nav links after expand:", nlinks)

        # ---- dashboard (already here after login) ----
        time.sleep(1)
        page.screenshot(path=str(OUT / "01_dashboard.png"), full_page=True)
        print("saved 01_dashboard.png")

        # ---- pages: click the sidebar link (keeps the session) ----
        import os
        only = set(os.environ.get("ONLY", "").split(",")) if os.environ.get("ONLY") else None
        for fname, link, settle in PAGES:
            if only and fname not in only:
                continue
            try:
                el = page.get_by_role("link", name=link, exact=True).first
                el.scroll_into_view_if_needed(timeout=10000)
                time.sleep(0.4)
                el.click(timeout=20000)
                time.sleep(settle)
                page.mouse.wheel(0, 200); time.sleep(0.6)
                page.mouse.wheel(0, -200); time.sleep(0.4)
                dest = OUT / f"{fname}.png"
                page.screenshot(path=str(dest), full_page=True)
                print("saved", dest.name)
            except Exception as e:
                print("FAILED", fname, "-", str(e)[:120])

        browser.close()


if __name__ == "__main__":
    run()
