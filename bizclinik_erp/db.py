"""SQLAlchemy 2.0 engine + session factory.

Single SQLite database, WAL mode, foreign keys enforced. The engine is
created lazily and cached so test runs can override BIZCLINIK_DB_PATH.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Single declarative base for all ORM models."""


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _conn_record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.db_url, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Context manager that yields a session and commits on success.

    Usage:
        with get_session() as s:
            s.add(Customer(name="Foo"))
    """
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
    """Create all tables that aren't there yet. Safe to call repeatedly."""
    # Import here so the model modules register with Base before create_all.
    from . import models  # noqa: F401
    Base.metadata.create_all(get_engine())


def reset_db() -> None:
    """DROP every table, then recreate. Destructive — use only for fresh setup."""
    from . import models  # noqa: F401
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
