"""SQLAlchemy 2.0 engine + session factory — tenant-aware.

Each call to get_session()/get_engine() resolves the active database from a
contextvar set per request (Streamlit script run / API request). When no
tenant is active the legacy single database at BIZCLINIK_DB_PATH is used, so
the original single-tenant deployment keeps working unchanged.

Engines + session factories are cached per resolved DB path. `cache_clear`
attributes are preserved on get_engine / _session_factory so the test
fixtures (which call `.cache_clear()`) keep working after the refactor.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import Numeric, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Single declarative base for all per-tenant ORM models."""


# Monetary column type. Stores as NUMERIC(18,2) — exact decimal on Postgres,
# matching the production decimalize migration — so newly provisioned tenants
# and fresh installs get exact money storage from create_all(). asdecimal=False
# keeps Python-side values as float, so the service layer needs no Decimal
# refactor and there is no Decimal/float mixing. Quantities, rates and scores
# intentionally stay Float (they are not 2dp money).
Money = Numeric(18, 2, asdecimal=False)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _conn_record):
    # Only meaningful for SQLite — skip silently for Postgres connections.
    if dbapi_conn.__class__.__module__.split(".")[0] not in ("sqlite3", "pysqlite2"):
        return
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    # Wait up to 5s for a competing writer's lock instead of failing immediately
    # with "database is locked" (dev/test backend).
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


# ---- active-tenant context ------------------------------------------------

# Holds the active database file path for the current execution context.
# None  -> use the legacy BIZCLINIK_DB_PATH (single-tenant / default).
_active_db_path: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "bizclinik_active_db_path", default=None
)


def set_active_db_path(path: Optional[str]) -> None:
    """Set (or clear with None) the active database for this context."""
    _active_db_path.set(str(path) if path else None)


def get_active_db_path() -> Optional[str]:
    return _active_db_path.get()


def _resolve_db_path() -> str:
    active = _active_db_path.get()
    if active:
        return active
    return str(get_settings().db_path)


# ---- per-path engine + factory caches -------------------------------------

_engines: dict[str, Engine] = {}
_factories: dict[str, "sessionmaker[Session]"] = {}


def _clear_caches() -> None:
    for eng in _engines.values():
        try:
            eng.dispose()
        except Exception:
            pass
    _engines.clear()
    _factories.clear()


def get_engine() -> Engine:
    from .dbbackend import is_sqlite, make_url
    path = _resolve_db_path()
    eng = _engines.get(path)
    if eng is None:
        url = make_url(path)
        if is_sqlite():
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            eng = create_engine(url, future=True)
        else:
            # Postgres: keep connections healthy across idle periods.
            eng = create_engine(url, future=True, pool_pre_ping=True)
        _engines[path] = eng
    return eng


def _session_factory() -> "sessionmaker[Session]":
    path = _resolve_db_path()
    fac = _factories.get(path)
    if fac is None:
        fac = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
        _factories[path] = fac
    return fac


# Preserve the lru_cache-style interface the test fixtures rely on.
get_engine.cache_clear = _clear_caches          # type: ignore[attr-defined]
_session_factory.cache_clear = _clear_caches    # type: ignore[attr-defined]


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session bound to the active tenant DB; commit on success."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables on the active DB + add any missing columns. Safe to
    call repeatedly (idempotent migration for additive schema changes)."""
    from . import models  # noqa: F401  (register models with Base)
    Base.metadata.create_all(get_engine())
    # Additive migration: ALTER TABLE ADD COLUMN for columns added to models
    # after a DB was first created (create_all never adds columns).
    from .services.migrate import ensure_schema
    ensure_schema(get_engine())


def reset_db() -> None:
    """DROP + recreate all tables on the active DB. Destructive."""
    from . import authz, models  # noqa: F401
    authz.require_perm("reset.db")
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
