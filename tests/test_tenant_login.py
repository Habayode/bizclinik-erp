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


def test_subdomain_resolution_helpers_exist():
    from bizclinik_erp import auth
    assert hasattr(auth, "_resolve_subdomain_slug")
    assert hasattr(auth, "_subdomain_from_request")
