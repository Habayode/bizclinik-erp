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

import hashlib
import re
import secrets
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, create_engine, select,
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


class ApiKey(ControlBase):
    """A REST-API key, optionally bound to a tenant. tenant_slug NULL means the
    key operates against the default/legacy DB. Only the SHA-256 hash is
    stored; the plaintext is shown once at creation."""
    __tablename__ = "api_key"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tenant_slug: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Subscription(ControlBase):
    """A tenant's SaaS subscription to a BizClinik plan. One row per tenant
    (latest state). Plan definitions/pricing live in services.billing.PLANS."""
    __tablename__ = "subscription"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/active/past_due/canceled
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BillingCharge(ControlBase):
    """A single payment attempt for a subscription, keyed by provider reference."""
    __tablename__ = "billing_charge"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_ngn: Mapped[float] = mapped_column(Float, default=0.0)
    provider: Mapped[str] = mapped_column(String(24), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/paid/failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


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


# ---- API keys -------------------------------------------------------------


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def create_api_key(tenant_slug: Optional[str], label: str = "") -> str:
    """Create an API key bound to a tenant (or None = default DB). Returns the
    plaintext key ONCE — only its hash is stored."""
    if tenant_slug:
        tenant_slug = tenant_slug.strip().lower()
        if not get_tenant(tenant_slug):
            raise ValueError(f"Tenant {tenant_slug!r} not found.")
    plaintext = "bzk_" + secrets.token_urlsafe(32)
    fac = _control_factory()
    with fac() as s:
        s.add(ApiKey(key_hash=_hash_key(plaintext), tenant_slug=tenant_slug,
                     label=label or ""))
        s.commit()
    return plaintext


def resolve_api_key(plaintext: str) -> Optional[dict]:
    """Look up an active API key by its plaintext. Returns
    {tenant_slug, label} or None. Updates last_used_at."""
    if not plaintext:
        return None
    h = _hash_key(plaintext)
    fac = _control_factory()
    with fac() as s:
        k = s.execute(
            select(ApiKey).where(ApiKey.key_hash == h,
                                  ApiKey.is_active == True)  # noqa: E712
        ).scalar_one_or_none()
        if not k:
            return None
        k.last_used_at = datetime.utcnow()
        s.commit()
        return {"tenant_slug": k.tenant_slug, "label": k.label}


def list_api_keys() -> list[dict]:
    fac = _control_factory()
    with fac() as s:
        return [{"id": k.id, "tenant_slug": k.tenant_slug, "label": k.label,
                 "is_active": k.is_active,
                 "created_at": str(k.created_at)[:19],
                 "last_used_at": str(k.last_used_at)[:19] if k.last_used_at else ""}
                for k in s.execute(select(ApiKey).order_by(ApiKey.id)).scalars()]


def revoke_api_key(key_id: int) -> None:
    fac = _control_factory()
    with fac() as s:
        k = s.get(ApiKey, key_id)
        if k:
            k.is_active = False
            s.commit()


# ---- adopt an existing DB as a tenant -------------------------------------


def adopt_db_as_tenant(slug: str, name: str, source_db_path: str) -> dict:
    """Register a tenant whose database is a COPY of an existing DB. Used to
    migrate the original single-tenant books into a named tenant without
    losing anything. The source DB is left untouched."""
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError("Invalid slug (lowercase letters/digits/hyphens, 2-41).")
    src = Path(source_db_path)
    if not src.exists():
        raise ValueError(f"Source DB not found: {source_db_path}")

    dest = Path(tenant_db_path(slug))
    fac = _control_factory()
    with fac() as s:
        if s.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none():
            raise ValueError(f"Tenant {slug!r} already exists.")

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Checkpoint the source WAL into the main file, then copy via the sqlite
    # backup API so we get a clean, consistent snapshot.
    src_conn = sqlite3.connect(str(src))
    try:
        src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass
    dst_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    with fac() as s:
        s.add(Tenant(slug=slug, name=name.strip(), db_path=str(dest)))
        s.commit()

    # Ensure schema is current on the adopted DB (idempotent migration).
    token = _db._active_db_path.set(str(dest))
    try:
        _db.init_db()
    finally:
        _db._active_db_path.reset(token)

    return {"slug": slug, "name": name.strip(), "db_path": str(dest)}
