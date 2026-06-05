"""Render docs/USER_MANUAL.md to a branded PDF using markdown + Chromium (Playwright)."""
from __future__ import annotations

from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent.parent / "docs"
MD = DOCS / "USER_MANUAL.md"
OUT = Path(__file__).resolve().parent.parent / "BizClinik_ERP_User_Manual.pdf"

CSS = """
@page { size: A4; margin: 16mm 14mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Calibri, Arial, sans-serif; color: #0F172A;
       font-size: 11pt; line-height: 1.45; }
h1 { color: #1F3864; font-size: 22pt; border-bottom: 3px solid #0EA5A4;
     padding-bottom: 4px; margin-top: 26px; }
h2 { color: #1F3864; font-size: 15pt; margin-top: 20px; }
h3 { color: #0EA5A4; font-size: 12.5pt; margin-top: 14px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; }
th, td { border: 1px solid #E5E7EB; padding: 5px 8px; text-align: left; }
th { background: #1F3864; color: #fff; }
tr:nth-child(even) td { background: #F4F6FB; }
code, pre { font-family: Consolas, monospace; background: #0B1220; color: #D1FAE5;
            border-radius: 4px; }
code { padding: 1px 4px; font-size: 9pt; }
pre { padding: 10px 12px; font-size: 9pt; overflow-x: auto; }
pre code { background: none; padding: 0; }
img { max-width: 100%; border: 1px solid #E5E7EB; border-radius: 6px;
      margin: 8px 0; box-shadow: 0 2px 8px rgba(15,23,42,0.08); }
blockquote { border-left: 4px solid #0EA5A4; margin: 8px 0; padding: 4px 12px;
             background: #F0FdFa; color: #334155; }
a { color: #2563EB; }
hr { border: none; border-top: 1px solid #E5E7EB; margin: 18px 0; }
"""


def build() -> None:
    html_body = markdown.markdown(
        MD.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<base href='{DOCS.as_uri()}/'><style>{CSS}</style></head>"
            f"<body>{html_body}</body></html>")
    tmp = DOCS / "_manual_render.html"
    tmp.write_text(html, encoding="utf-8")
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(tmp.as_uri(), wait_until="networkidle")
            pg.pdf(path=str(OUT), format="A4", print_background=True,
                   margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
            b.close()
        print("wrote", OUT, f"({OUT.stat().st_size // 1024} KB)")
    finally:
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    build()
