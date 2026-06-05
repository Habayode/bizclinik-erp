"""_subdomain_from_request maps <slug>.erp.<zone> hosts to a tenant slug."""
from __future__ import annotations

import types

import pytest


class _FakeContext:
    def __init__(self, host):
        self.headers = {"host": host}


def _patch_host(monkeypatch, host):
    import bizclinik_erp.auth as auth
    fake_st = types.SimpleNamespace(context=_FakeContext(host))
    monkeypatch.setattr(auth, "st", fake_st)


@pytest.mark.parametrize("host,expected", [
    # nested layout (current hagai.online free-TLS scheme)
    ("wendysrack.erp.hagai.online", "wendysrack"),
    ("acme.erp.hagai.online", "acme"),
    ("ACME.ERP.HAGAI.ONLINE", "acme"),          # case-insensitive
    ("acme.erp.hagai.online:8501", "acme"),      # port stripped
    ("acme.erp.hagai.online.", "acme"),          # trailing dot tolerated
    # flat layout (future dedicated domain, one level -> free Universal SSL)
    ("acme.bizclinik.app", "acme"),
    ("wendysrack.example.com", "wendysrack"),
    # reserved / infra labels -> picker, never a tenant
    ("erp.hagai.online", None),
    ("api.hagai.online", None),
    ("www.bizclinik.app", None),
    # apex / non-host -> picker
    ("hagai.online", None),                       # 2 labels = apex
    ("localhost", None),
    ("165.227.224.154", None),                    # bare IPv4
])
def test_subdomain_extraction(monkeypatch, host, expected):
    _patch_host(monkeypatch, host)
    from bizclinik_erp.auth import _subdomain_from_request
    assert _subdomain_from_request() == expected


def test_no_headers_returns_none(monkeypatch):
    import bizclinik_erp.auth as auth

    class _Boom:
        @property
        def headers(self):
            raise RuntimeError("no context")

    monkeypatch.setattr(auth, "st", types.SimpleNamespace(context=_Boom()))
    from bizclinik_erp.auth import _subdomain_from_request
    assert _subdomain_from_request() is None
