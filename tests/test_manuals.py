"""The in-app User Manual is tenant-aware: school tenants get the school manual,
everyone else the standard one, with a safe fallback."""
from __future__ import annotations

from bizclinik_erp import manuals


def test_school_gets_school_manual():
    spec = manuals.manual_for("school")
    assert spec["md"].name == "USER_MANUAL_SCHOOL.md"
    assert spec["pdf_name"] == "Trakit365_School_ERP_User_Manual.pdf"
    assert "School" in spec["title"]


def test_general_gets_standard_manual():
    for v in ("general", None, "retail"):
        spec = manuals.manual_for(v)
        assert spec["md"].name == "USER_MANUAL.md"
        assert spec["pdf_name"] == "Trakit365_ERP_User_Manual.pdf"


def test_school_manual_file_actually_ships():
    # The school markdown must exist in the repo (the page reads it live).
    assert manuals.manual_for("school")["md"].exists()


def test_falls_back_to_standard_when_school_file_missing(tmp_path):
    # A school tenant on a box without the school file still gets a manual.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "USER_MANUAL.md").write_text("# Manual", encoding="utf-8")
    spec = manuals.manual_for("school", root=tmp_path)
    assert spec["md"].name == "USER_MANUAL.md"
