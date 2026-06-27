"""User accounts service: create, authenticate, manage sessions.

Password hashing uses PBKDF2-HMAC-SHA256, 200k iterations, 24-byte random
salt. Format stored in `password_hash`:
    pbkdf2_sha256$<iterations>$<b64_salt>$<b64_hash>

Session tokens are 32-byte URL-safe random strings stored in user_session.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.users import Role, User, UserSession
from .audit import record
from ..models.audit import AuditAction


# ---- password hashing ------------------------------------------------------


_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 24
_HASH_BYTES = 32
_HASH_PREFIX = "pbkdf2_sha256"


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("Password cannot be empty.")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt,
                             _PBKDF2_ITERATIONS, dklen=_HASH_BYTES)
    return (
        f"{_HASH_PREFIX}${_PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(plain: str, stored: str) -> bool:
    if not stored or not plain:
        return False
    try:
        scheme, iter_str, b64_salt, b64_hash = stored.split("$", 3)
    except ValueError:
        return False
    if scheme != _HASH_PREFIX:
        return False
    try:
        iterations = int(iter_str)
        salt = base64.b64decode(b64_salt)
        expected = base64.b64decode(b64_hash)
    except (ValueError, base64.binascii.Error):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt,
                                  iterations, dklen=len(expected))
    return hmac.compare_digest(actual, expected)


# ---- user management ------------------------------------------------------


def create_user(
    session: Session, *,
    username: str, password: str, role: Role | str = Role.VIEWER,
    email: Optional[str] = None, full_name: Optional[str] = None,
    must_change_password: bool = False,
    created_by_user_id: Optional[int] = None,
) -> User:
    username = (username or "").strip().lower()
    if not username:
        raise ValueError("Username required.")
    existing = session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if existing:
        raise ValueError(f"Username {username!r} already exists.")
    if isinstance(role, str):
        role = Role(role)
    user = User(
        username=username,
        email=email, full_name=full_name,
        role=role,
        password_hash=hash_password(password),
        must_change_password=must_change_password,
        created_by_user_id=created_by_user_id,
    )
    session.add(user)
    session.flush()
    record(session, action=AuditAction.CREATE, entity_type="user",
           entity_id=user.id, description=f"Created user {user.username} ({user.role.value})",
           user_id=created_by_user_id, source="services.users")
    return user


def set_password(session: Session, user_id: int, new_password: str,
                  acting_user_id: Optional[int] = None) -> None:
    user = session.get(User, user_id)
    if not user:
        raise ValueError("User not found.")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    record(session, action=AuditAction.UPDATE, entity_type="user",
           entity_id=user.id, description="Password changed",
           user_id=acting_user_id, source="services.users")


def get_welcome_prefs(session: Session, user_id: int) -> tuple[bool, bool]:
    """(show_banner, speak_aloud) for the login welcome. Defaults to (True, True)."""
    user = session.get(User, user_id)
    if not user:
        return True, True
    return (bool(getattr(user, "welcome_show", True)),
            bool(getattr(user, "welcome_voice", True)))


def set_welcome_prefs(session: Session, user_id: int, *, show: bool,
                      voice: bool) -> None:
    """Self-service: update the current user's login-welcome preferences."""
    user = session.get(User, user_id)
    if not user:
        raise ValueError("User not found.")
    user.welcome_show = bool(show)
    user.welcome_voice = bool(voice)
    session.flush()


def set_role(session: Session, user_id: int, role: Role | str,
              acting_user_id: Optional[int] = None) -> None:
    user = session.get(User, user_id)
    if not user:
        raise ValueError("User not found.")
    if isinstance(role, str):
        role = Role(role)
    user.role = role
    record(session, action=AuditAction.UPDATE, entity_type="user",
           entity_id=user.id, description=f"Role changed to {role.value}",
           user_id=acting_user_id, source="services.users")


def deactivate(session: Session, user_id: int,
                acting_user_id: Optional[int] = None) -> None:
    user = session.get(User, user_id)
    if not user:
        return
    user.is_active = False
    record(session, action=AuditAction.UPDATE, entity_type="user",
           entity_id=user.id, description="Deactivated",
           user_id=acting_user_id, source="services.users")


def list_users(session: Session, *, include_inactive: bool = False) -> list[User]:
    q = select(User).order_by(User.username)
    if not include_inactive:
        q = q.where(User.is_active == True)  # noqa: E712
    return list(session.execute(q).scalars())


# ---- authentication ------------------------------------------------------


_MAX_FAILS = 5
_LOCK_MINUTES = 15
_SESSION_LIFETIME_HOURS = 12


def authenticate(session: Session, username: str, password: str,
                  *, ip_address: Optional[str] = None,
                  user_agent: Optional[str] = None) -> Optional[UserSession]:
    """Returns a fresh UserSession on success, None on failure.

    Failure cases log an audit entry. Account locks after 5 consecutive
    failures for 15 minutes.
    """
    username = (username or "").strip().lower()
    if not username:
        return None
    user = session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if not user or not user.is_active:
        record(session, action=AuditAction.LOGIN_FAILED, entity_type="user",
               description=f"Login attempt for unknown/inactive user {username!r}",
               username=username, source="services.users")
        return None
    now = datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        record(session, action=AuditAction.LOGIN_FAILED, entity_type="user",
               entity_id=user.id,
               description="Login attempt while account is locked",
               user_id=user.id, username=user.username, source="services.users")
        return None
    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= _MAX_FAILS:
            user.locked_until = now + timedelta(minutes=_LOCK_MINUTES)
        record(session, action=AuditAction.LOGIN_FAILED, entity_type="user",
               entity_id=user.id, description="Wrong password",
               user_id=user.id, username=user.username, source="services.users")
        return None

    # Success.
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    sess = UserSession(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        expires_at=now + timedelta(hours=_SESSION_LIFETIME_HOURS),
        ip_address=ip_address, user_agent=user_agent,
    )
    session.add(sess)
    record(session, action=AuditAction.LOGIN, entity_type="user",
           entity_id=user.id, description=f"Logged in as {user.role.value}",
           user_id=user.id, username=user.username, source="services.users")
    return sess


def lookup_session(session: Session, token: str) -> Optional[UserSession]:
    if not token:
        return None
    s = session.execute(
        select(UserSession).where(UserSession.token == token)
    ).scalar_one_or_none()
    if not s or s.revoked_at:
        return None
    now = datetime.utcnow()
    if s.expires_at and s.expires_at < now:
        return None
    s.last_seen_at = now
    return s


def logout(session: Session, token: str) -> None:
    s = session.execute(
        select(UserSession).where(UserSession.token == token)
    ).scalar_one_or_none()
    if s and not s.revoked_at:
        s.revoked_at = datetime.utcnow()
        record(session, action=AuditAction.LOGOUT, entity_type="user",
               entity_id=s.user_id, user_id=s.user_id, source="services.users")


def ensure_bootstrap_admin(session: Session, *, password: str) -> User:
    """Idempotent: create the default `admin` user if none exists yet."""
    existing = session.execute(select(User).limit(1)).scalar_one_or_none()
    if existing:
        return existing
    return create_user(session, username="admin", password=password,
                        role=Role.ADMIN, full_name="System Administrator")
