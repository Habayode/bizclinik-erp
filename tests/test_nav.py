"""Tenant-aware navigation spec — school-first for school tenants, standard and
School-free for general tenants."""
from __future__ import annotations

from bizclinik_erp.nav import build_nav_spec


def _paths(spec):
    return [p["path"] for _, pages in spec for p in pages]


def test_school_vertical_is_school_first_and_curated():
    spec = build_nav_spec("school")
    groups = [g for g, _ in spec]
    assert "School" in groups
    # School sits above the accounting group.
    assert groups.index("School") < groups.index("Accounts & Finance")
    paths = _paths(spec)
    assert any("30_School_Setup" in p for p in paths)
    assert any("37_School_Notifications" in p for p in paths)
    # School-irrelevant modules are hidden.
    assert not any("23_CRM" in p for p in paths)
    assert not any("9_FIRS" in p for p in paths)
    assert not any("20_Currencies" in p for p in paths)
    # Bursary essentials remain.
    assert any("10_General_Ledger" in p for p in paths)
    assert any("4_Banking" in p for p in paths)


def test_general_vertical_hides_school_keeps_full_finance():
    spec = build_nav_spec("general")
    groups = [g for g, _ in spec]
    assert "School" not in groups            # general tenants never see School
    paths = _paths(spec)
    assert any("23_CRM" in p for p in paths)
    assert any("9_FIRS" in p for p in paths)
    assert any("20_Currencies" in p for p in paths)


def test_unknown_vertical_defaults_to_general():
    assert [g for g, _ in build_nav_spec("retail")] == \
           [g for g, _ in build_nav_spec("general")]


def test_exactly_one_default_landing():
    for v in ("school", "general"):
        defaults = [p for _, pages in build_nav_spec(v) for p in pages if p["default"]]
        assert len(defaults) == 1


def test_company_has_vertical_field_default_general(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Company
    with get_session() as s:
        c = Company(name="Acme"); s.add(c); s.flush()
        assert c.vertical == "general"
