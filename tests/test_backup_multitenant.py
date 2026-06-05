"""snapshot_all backs up the default DB, control plane, and every tenant DB."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def mt_env(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setenv("BIZCLINIK_DB_PATH", str(db_path))
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    from bizclinik_erp import tenancy, db as _db
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
    tenancy._reset_control_cache()
    # bootstrap default DB
    from bizclinik_erp.services.bootstrap import bootstrap
    bootstrap(admin_password="x")
    yield tmp_path
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
    tenancy._reset_control_cache()
    _db.set_active_db_path(None)


def test_snapshot_all_covers_default_and_tenants(mt_env):
    from bizclinik_erp import tenancy
    from bizclinik_erp.services import backup

    tenancy.create_tenant("alpha", "Alpha", admin_password="pw")
    tenancy.create_tenant("beta", "Beta", admin_password="pw")

    dest = mt_env / "backups"
    results = backup.snapshot_all(dest_root=dest)
    scopes = {r["scope"] for r in results if "error" not in r}

    assert "default" in scopes
    assert "control" in scopes
    assert "tenant-alpha" in scopes
    assert "tenant-beta" in scopes

    # Each scope has a snapshot file on disk.
    for scope in scopes:
        folder = dest / scope
        snaps = backup.list_snapshots(folder)
        assert len(snaps) >= 1, f"no snapshot for {scope}"
        assert snaps[-1].stat().st_size > 0


def test_snapshot_all_single_tenant_ok(mt_env):
    """With no tenants registered, snapshot_all still backs up the default DB."""
    from bizclinik_erp.services import backup
    dest = mt_env / "backups"
    results = backup.snapshot_all(dest_root=dest)
    scopes = {r["scope"] for r in results if "error" not in r}
    assert "default" in scopes
