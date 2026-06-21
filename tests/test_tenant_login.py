"""The pre-login screen must not enumerate tenants — a visitor cannot see the
list of businesses on the platform (security: tenant enumeration). Businesses
are reached by their own subdomain or by typing their business ID."""
from __future__ import annotations

import inspect


def test_tenant_picker_does_not_list_tenants():
    from bizclinik_erp import auth
    src = inspect.getsource(auth._tenant_picker)
    assert "list_tenants" not in src, \
        "login must not call tenancy.list_tenants() (no tenant enumeration)"
    assert "selectbox" not in src, \
        "login must not show a dropdown of all businesses"
    # It validates a typed business ID against the registry instead.
    assert "get_tenant" in src


def test_demo_form_has_honeypot():
    from bizclinik_erp import auth
    import inspect
    src = inspect.getsource(auth._tenant_picker)
    assert "demo_hp" in src and "create_demo_request" in src


def test_subdomain_resolution_helpers_exist():
    from bizclinik_erp import auth
    assert hasattr(auth, "_resolve_subdomain_slug")
    assert hasattr(auth, "_subdomain_from_request")


def test_login_screen_offers_request_demo():
    import inspect
    from bizclinik_erp import auth
    src = inspect.getsource(auth._tenant_picker)
    assert "Request a demo" in src and "create_demo_request" in src


def test_demo_request_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(tmp_path / "legacy.db"))
    from bizclinik_erp.config import get_settings
    from bizclinik_erp import tenancy
    get_settings.cache_clear(); tenancy._reset_control_cache()
    try:
        rid = tenancy.create_demo_request(
            name="Jane Bursar", business="Sunrise School",
            email="jane@example.com", phone="08000000000",
            message="Interested in the school edition")
        rows = tenancy.list_demo_requests()
        match = [r for r in rows if r["id"] == rid]
        assert match and match[0]["business"] == "Sunrise School"
        assert match[0]["name"] == "Jane Bursar" and match[0]["status"] == "new"
    finally:
        tenancy._reset_control_cache(); get_settings.cache_clear()


def test_slug_candidates_accepts_id_erp_and_url():
    from bizclinik_erp import auth
    for entry in ("otasch", "OTASCH", "otasch-erp", "otasch-erp.hagai.online",
                  "https://otasch-erp.hagai.online/Dashboard",
                  "  otasch-erp.hagai.online/  "):
        assert "otasch" in auth._slug_candidates(entry), entry
    assert auth._slug_candidates("") == []
    # a plain id with no -erp / host still works
    assert auth._slug_candidates("wendysrack") == ["wendysrack"]
