"""Multi-tenant control plane.

A small registry (its own SQLite at <data>/control.db) lists tenants. Each
tenant has an isolated database at <data>/tenants/<slug>/bizclinik.db with the
full schema + its own users. The control DB never holds business data.

Activation: `set_active(slug)` points the db-layer contextvar at that tenant's
DB; everything downstream (services, pages) then reads/writes that tenant in
total isolation. `set_active(None)` falls back to the legacy single DB, so a
deployment with zero tenants behaves exactly like the original single-tenant
app.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Integer, String, create_engine, select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings
from . import db as _db


class ControlBase(DeclarativeBase):
    """Separate base so the tenant registry never lands in tenant DBs."""


class Tenant(ControlBase):
    __tablename__ = "tenant"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---- control engine (cached per resolved control.db path) -----------------

_control_engines: dict[str, Engine] = {}
_control_factories: dict[str, "sessionmaker"] = {}


def _control_db_path() -> Path:
    return Path(get_settings().db_path).parent / "control.db"


def _control_factory():
    path = str(_control_db_path())
    fac = _control_factories.get(path)
    if fac is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(f"sqlite:///{path}", future=True)
        ControlBase.metadata.create_all(eng)
        _control_engines[path] = eng
        fac = sessionmaker(bind=eng, expire_on_commit=False, future=True)
        _control_factories[path] = fac
    return fac


def _reset_control_cache() -> None:
    for e in _control_engines.values():
        try:
            e.dispose()
        except Exception:
            pass
    _control_engines.clear()
    _control_factories.clear()


# ---- registry API ---------------------------------------------------------


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def tenant_db_path(slug: str) -> str:
    base = Path(get_settings().db_path).parent
    return str(base / "tenants" / slug / "bizclinik.db")


def list_tenants(*, active_only: bool = True) -> list[dict]:
    fac = _control_factory()
    with fac() as s:
        q = select(Tenant).order_by(Tenant.name)
        if active_only:
            q = q.where(Tenant.is_active == True)  # noqa: E712
        return [{"slug": t.slug, "name": t.name, "db_path": t.db_path,
                 "is_active": t.is_active,
                 "created_at": t.created_at} for t in s.execute(q).scalars()]


def get_tenant(slug: str) -> Optional[dict]:
    fac = _control_factory()
    with fac() as s:
        t = s.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
        if not t:
            return None
        return {"slug": t.slug, "name": t.name, "db_path": t.db_path,
                "is_active": t.is_active}


def has_tenants() -> bool:
    return len(list_tenants()) > 0


def create_tenant(slug: str, name: str, *, admin_password: str) -> dict:
    """Register a tenant and bootstrap its isolated database (schema + seed +
    admin user). Idempotent on the bootstrap; raises if the slug exists."""
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError(
            "Slug must be lowercase letters/digits/hyphens, 2-41 chars, "
            "starting alphanumeric (e.g. 'acme-ltd')."
        )
    if not name.strip():
        raise ValueError("Tenant name required.")

    path = tenant_db_path(slug)
    fac = _control_factory()
    with fac() as s:
        if s.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none():
            raise ValueError(f"Tenant {slug!r} already exists.")
        s.add(Tenant(slug=slug, name=name.strip(), db_path=path))
        s.commit()

    # Bootstrap the tenant DB inside its own active-path context.
    token = _db._active_db_path.set(path)
    try:
        from .services.bootstrap import bootstrap
        bootstrap(admin_password=admin_password)
    finally:
        _db._active_db_path.reset(token)

    return {"slug": slug, "name": name.strip(), "db_path": path}


def deactivate_tenant(slug: str) -> None:
    fac = _control_factory()
    with fac() as s:
        t = s.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
        if t:
            t.is_active = False
            s.commit()


# ---- activation -----------------------------------------------------------


def set_active(slug: Optional[str]) -> None:
    """Point the db layer at the given tenant (or None for legacy default)."""
    if not slug:
        _db.set_active_db_path(None)
        return
    t = get_tenant(slug)
    _db.set_active_db_path(t["db_path"] if t else None)
