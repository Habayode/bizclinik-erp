"""Database backend selection — SQLite (default) or PostgreSQL.

The rest of the app routes every connection through a *key* (today: the SQLite
file path that tenancy assigns each tenant). This module turns that key into a
SQLAlchemy URL for the configured backend, so switching to Postgres is a config
change, not a rewrite of db.py / tenancy.py.

Backend is chosen by ``BIZCLINIK_DB_BACKEND`` (``sqlite`` | ``postgres``;
default ``sqlite``). In Postgres mode we use **database-per-tenant** — the same
isolation model as the per-tenant SQLite files — deriving a stable Postgres
database name from the routing key:

    <data>/bizclinik.db                          -> <prefix>            (default DB)
    <data>/control.db                            -> <prefix>_control
    <data>/tenants/<slug>/bizclinik.db           -> <prefix>_t_<slug>

Postgres connection env: PGHOST, PGPORT, PGUSER, PGPASSWORD, plus
``BIZCLINIK_PG_PREFIX`` (default ``bizclinik``).
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote


def backend() -> str:
    return (os.environ.get("BIZCLINIK_DB_BACKEND") or "sqlite").strip().lower()


def is_postgres() -> bool:
    return backend() == "postgres"


def is_sqlite() -> bool:
    return not is_postgres()


def _safe(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", str(name).lower()).strip("_") or "x"


def _prefix() -> str:
    return _safe(os.environ.get("BIZCLINIK_PG_PREFIX") or "bizclinik")


def pg_dbname_for(key: str) -> str:
    """Deterministic Postgres database name for a routing key (a SQLite path)."""
    p = str(key).replace("\\", "/")
    low = p.lower()
    prefix = _prefix()
    if low.endswith("control.db"):
        return f"{prefix}_control"
    if "/tenants/" in low:
        slug = _safe(p.split("/tenants/")[1].split("/")[0])
        return f"{prefix}_t_{slug}"[:63]
    return prefix


def pg_admin_url(dbname: str = "postgres") -> str:
    """URL to a maintenance DB (for CREATE DATABASE / server-level ops)."""
    return _pg_url(dbname)


def _pg_url(dbname: str) -> str:
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "bizclinik")
    pw = os.environ.get("PGPASSWORD", "")
    auth = ""
    if user:
        auth = quote(user, safe="") + (f":{quote(pw, safe='')}" if pw else "") + "@"
    return f"postgresql+psycopg://{auth}{host}:{port}/{dbname}"


def make_url(key: str) -> str:
    """SQLAlchemy URL for a routing key, per the configured backend."""
    if is_postgres():
        return _pg_url(pg_dbname_for(key))
    return f"sqlite:///{key}"
