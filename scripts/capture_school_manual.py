"""Capture school-manual screenshots from a live school tenant via Playwright.

Designed to run ON the droplet against the public OTASCH site (the subdomain
auto-selects the tenant and shows the school-branded login). Logs in, visits each
School page, and saves PNGs into docs/school_images/.

    BASE=https://otasch-erp.hagai.online SCHOOL_USER=admin SCHOOL_PW=... \
        PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
        ./venv/bin/python scripts/capture_school_manual.py
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "https://otasch-erp.hagai.online")
USER = os.environ.get("SCHOOL_USER", "admin")
PW = os.environ.get("SCHOOL_PW", "")
OUT = Path(__file__).resolve().parent.parent / "docs" / "school_images"
OUT.mkdir(parents=True, exist_ok=True)

# (filename, sidebar-link-text, settle-seconds). Navigate by CLICK to keep the
# Streamlit session. Link names match the school nav in bizclinik_erp/nav.py.
PAGES = [
    ("02_school_setup", "School Setup", 4),
    ("03_students", "Students", 4),
    ("04_school_fees", "School Fees", 4),
    ("05_attendance", "Attendance", 4),
    ("06_results", "Results", 4),
    ("07_teachers", "Teachers", 4),
    ("08_parent_notifications", "Parent Notifications", 4),
]


def run() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000},
                                  device_scale_factor=1)
        page = ctx.new_page()

        # ---- login (subdomain auto-selects the school tenant) ----
        page.goto(BASE, wait_until="domcontentloaded")
        time.sleep(7)
        try:
            page.fill('input[aria-label="Username"]', USER, timeout=15000)
            page.fill('input[aria-label="Password"]', PW, timeout=15000)
            page.get_by_role("button", name="Sign in").first.click()
            time.sleep(7)
            print("logged in")
        except Exception as e:
            print("login step:", e)

        # ---- expand the collapsed sidebar nav ("View N more") ----
        for _ in range(3):
            try:
                page.locator('[data-testid="stSidebarNav"]').get_by_text(
                    re.compile(r"View .*more", re.I)).first.click(timeout=4000)
                time.sleep(1.0)
                break
            except Exception:
                try:
                    page.get_by_text(re.compile(r"View .*more", re.I)).first.click(timeout=4000)
                    time.sleep(1.0); break
                except Exception:
                    time.sleep(1.0)
        nlinks = page.locator('[data-testid="stSidebarNav"] a').count()
        print("nav links after expand:", nlinks)

        # ---- School Dashboard (the default landing after login) ----
        time.sleep(1)
        page.screenshot(path=str(OUT / "01_school_dashboard.png"), full_page=True)
        print("saved 01_school_dashboard.png")

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
                print("FAILED", fname, "-", str(e)[:140])

        browser.close()


if __name__ == "__main__":
    run()
