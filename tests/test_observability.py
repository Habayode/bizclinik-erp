"""init_sentry is a safe no-op without a DSN and never raises."""
from __future__ import annotations


def test_no_dsn_is_noop(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    import importlib
    from bizclinik_erp import observability
    importlib.reload(observability)
    assert observability.init_sentry("test") is False


def test_blank_dsn_is_noop(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "   ")
    import importlib
    from bizclinik_erp import observability
    importlib.reload(observability)
    assert observability.init_sentry("test") is False


def test_dsn_set_but_sdk_missing_is_graceful(monkeypatch):
    # A DSN is set but if sentry_sdk import/init fails, we must not raise.
    monkeypatch.setenv("SENTRY_DSN", "https://example@o0.ingest.sentry.io/0")
    import importlib
    from bizclinik_erp import observability
    importlib.reload(observability)
    # Returns True if sentry-sdk happens to be installed and inits, else False —
    # either way it must not raise.
    result = observability.init_sentry("test")
    assert result in (True, False)
