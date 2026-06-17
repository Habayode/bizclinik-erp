"""Which User Manual to serve, per tenant vertical.

Pure + path-based so it is unit-testable. A ``school`` tenant gets the
school-specific manual (and its PDF); everyone else gets the standard one. Falls
back to the standard manual if the school file isn't present, so a school tenant
is never left without a manual.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"

_GENERAL = {
    "md": "docs/USER_MANUAL.md",
    "pdf": "Trakit365_ERP_User_Manual.pdf",
    "title": "User Manual",
    "subtitle": "The complete illustrated guide",
}
_SCHOOL = {
    "md": "docs/USER_MANUAL_SCHOOL.md",
    "pdf": "Trakit365_School_ERP_User_Manual.pdf",
    "title": "School User Manual",
    "subtitle": "Running your school on Trakit365 — fees, students & more",
}


def manual_for(vertical: str | None, *, root: Path = _ROOT) -> dict:
    """Return {md, pdf, title, subtitle} (md/pdf are absolute Paths) for the
    given tenant vertical. School tenants get the school manual when its file
    exists, else fall back to the standard manual."""
    spec = _SCHOOL if (vertical or "general") == "school" else _GENERAL
    if spec is _SCHOOL and not (root / _SCHOOL["md"]).exists():
        spec = _GENERAL
    return {
        "md": root / spec["md"],
        "pdf": root / spec["pdf"],
        "md_name": Path(spec["md"]).name,
        "pdf_name": spec["pdf"],
        "title": spec["title"],
        "subtitle": spec["subtitle"],
    }
