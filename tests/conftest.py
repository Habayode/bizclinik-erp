"""Shared pytest fixtures: fresh sqlite DB per test, configured via env var
before any bizclinik_erp module is imported."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_authz_actor():
    """Clear the service-layer actor before and after every test. The actor role
    lives in a contextvar that would otherwise leak across tests in the same
    process — and a leaked tenant actor now (correctly) blocks control-plane
    calls like tenancy.create_tenant via authz.require_platform()."""
    from bizclinik_erp import authz
    authz.clear_actor()
    yield
    authz.clear_actor()


@pytest.fixture
def fresh_db(monkeypatch):
    """Point BIZCLINIK_DB_PATH at a brand-new sqlite file, clear all cached
    engines/sessions, run migrations + seed. Yields nothing — tests then
    `from bizclinik_erp.db import get_session` and operate against the temp DB.
    """
    tmpdir = tempfile.mkdtemp(prefix="bizclinik_test_")
    db_path = Path(tmpdir) / "test.db"
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(db_path))

    # Clear all the lru_cache'd factories so they see the new env var.
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory, reset_db
    from bizclinik_erp.services.seed import seed_defaults
    from bizclinik_erp.db import get_session

    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()

    reset_db()
    with get_session() as s:
        seed_defaults(s)

    yield db_path

    # Tear down caches so the next test starts clean.
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
