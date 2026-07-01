"""Tenant-aware navigation spec — school-first for school tenants, standard and
School-free for general tenants."""
from __future__ import annotations

from bizclinik_erp.nav import build_nav_spec


def _paths(spec):
    return [p["path"] for _, pages in spec for p in pages]


def test_every_nav_path_resolves_to_a_real_file():
    """Guards the views/ layout: every page st.navigation references must exist
    on disk, for every vertical and operator/non-operator view. A stale path
    here would crash Home.py on every page (full outage), so keep it green."""
    import pathlib
    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    seen = set()
    for vertical in ("school", "general"):
        for pa in (True, False):
            for p in _paths(build_nav_spec(vertical, platform_admin=pa)):
                seen.add(p)
    missing = [p for p in seen if not (app_dir / p).exists()]
    assert not missing, f"nav paths with no file under app/: {missing}"
    # Sanity: the rename took — pages live under views/, not pages/.
    assert all(p.startswith("views/") for p in seen), \
        f"unexpected non-views path(s): {[p for p in seen if not p.startswith('views/')]}"


def test_school_vertical_is_school_first_and_curated():
    spec = build_nav_spec("school")
    groups = [g for g, _ in spec]
    # School is the very first group; accounting lives under "Bursary".
    assert groups[0] == "School"
    assert "Bursary" in groups and groups.index("School") < groups.index("Bursary")
    paths = _paths(spec)
    assert any("29_School_Dashboard" in p for p in paths)   # the school landing
    assert any("30_School_Setup" in p for p in paths)
    assert any("37_School_Notifications" in p for p in paths)
    # School-irrelevant modules are hidden.
    assert not any("23_CRM" in p for p in paths)
    assert not any("9_FIRS" in p for p in paths)
    assert not any("20_Currencies" in p for p in paths)
    # Bursary essentials remain (incl. the generic finance dashboard).
    assert any("10_General_Ledger" in p for p in paths)
    assert any("4_Banking" in p for p in paths)
    assert any("0_Dashboard" in p for p in paths)
    # The default landing is the School Dashboard, not the finance one.
    default = [p for _, pages in spec for p in pages if p["default"]][0]
    assert "29_School_Dashboard" in default["path"]


def test_general_vertical_hides_school_keeps_full_finance():
    spec = build_nav_spec("general")
    groups = [g for g, _ in spec]
    assert "School" not in groups            # general tenants never see School
    paths = _paths(spec)
    assert any("23_CRM" in p for p in paths)
    assert any("9_FIRS" in p for p in paths)
    assert any("20_Currencies" in p for p in paths)


def test_unknown_vertical_defaults_to_general():
    # An unrecognised vertical falls through to the general layout.
    assert [g for g, _ in build_nav_spec("wholesale")] == \
           [g for g, _ in build_nav_spec("general")]


def test_exactly_one_default_landing():
    for v in ("school", "general", "retail"):
        defaults = [p for _, pages in build_nav_spec(v) for p in pages if p["default"]]
        assert len(defaults) == 1


def test_company_has_vertical_field_default_general(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import Company
    with get_session() as s:
        c = Company(name="Acme"); s.add(c); s.flush()
        assert c.vertical == "general"
