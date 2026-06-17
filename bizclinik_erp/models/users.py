"""User accounts + roles.

Five-role model designed for SME accounting workflows:
    ADMIN      — everything, including period close + user management
    ACCOUNTANT — all GL postings, reports, master records
    SALES      — quotations, sales orders, invoices, receipts only
    AP         — purchase orders, bills, payments only
    VIEWER     — read-only access to reports and master records

Passwords are hashed with PBKDF2-HMAC-SHA256 (24-byte salt, 200k iterations).
Sessions are tracked in the DB so admins can revoke without touching the
user's password.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    ACCOUNTANT = "ACCOUNTANT"
    SALES = "SALES"
    AP = "AP"
    VIEWER = "VIEWER"


# What each role is allowed to do. Pages call `can(user, perm)` to gate
# the UI; services should ALSO verify before mutating data.
PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {
        "view.dashboard", "manage.users", "manage.company", "manage.settings",
        "post.invoice", "post.bill", "post.receipt", "post.payment", "post.journal",
        "void.any", "close.period", "lock.period", "reopen.period",
        "manage.coa", "manage.products", "manage.customers", "manage.suppliers",
        "manage.banks", "manage.employees", "manage.assets",
        "run.payroll", "run.depreciation", "import.data", "reset.db",
        "view.reports", "view.audit", "export.pdf", "manage.school",
    },
    Role.ACCOUNTANT: {
        "view.dashboard", "post.invoice", "post.bill", "post.receipt", "post.payment",
        "post.journal", "void.any", "manage.coa", "manage.products", "manage.customers",
        "manage.suppliers", "manage.banks", "manage.employees", "manage.assets",
        "run.payroll", "run.depreciation", "view.reports", "view.audit", "export.pdf",
        "import.data", "manage.school",
    },
    Role.SALES: {
        "view.dashboard", "post.invoice", "post.receipt", "manage.customers",
        "view.reports", "export.pdf",
    },
    Role.AP: {
        "view.dashboard", "post.bill", "post.payment", "manage.suppliers",
        "view.reports", "export.pdf",
    },
    Role.VIEWER: {
        "view.dashboard", "view.reports", "export.pdf",
    },
}


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.VIEWER)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))

    def has_perm(self, perm: str) -> bool:
        return perm in PERMISSIONS.get(self.role, set())

    def __repr__(self) -> str:
        return f"<User {self.username} {self.role.value}>"


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(256))

    user: Mapped[User] = relationship()
