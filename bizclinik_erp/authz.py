"""Service-layer authorization.

A contextvar holds the current actor's role; mutating services call
``require_perm()`` so the role/permission matrix is enforced no matter the entry
point — Streamlit UI, REST API, or anything else — not just at the page.

Fail-open for system contexts: when NO actor role is set (CLI, scheduled jobs,
internal seed/migration code, and the test-suite), permission is GRANTED. Only
an explicitly-set interactive (UI) or API actor is restricted. This lets us add
defense-in-depth checks inside services without breaking non-interactive
callers, and keeps the matrix definition in one place (models.users.PERMISSIONS).

Set the actor at the boundary:
  * Streamlit: auth.require_login() sets the logged-in user's role each run.
  * REST API: the request handler sets the key's role (full-access today).
"""
from __future__ import annotations

import contextvars
from typing import Optional

_actor_role: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "bizclinik_actor_role", default=None)

# Whether the current actor is the PLATFORM OPERATOR (manages all tenants), as
# opposed to a tenant-level admin. Set true only for an allow-listed operator
# session (see auth.is_platform_admin). Never granted by the role matrix — a
# tenant ADMIN is not a platform admin.
_platform_admin: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "bizclinik_platform_admin", default=False)

# Whether we are inside an interactive request (a Streamlit page run or a REST
# API request). Set True at those boundaries. When True but NO actor role is
# bound, permission checks fail CLOSED — an interactive entry point that forgot
# to bind an actor is denied rather than running unrestricted. CLI / scheduled
# jobs / seed / migrations / tests never set this, so they keep the break-glass.
_request_context: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "bizclinik_request_context", default=False)


class PermissionDenied(PermissionError):
    """Raised by require_perm() when the current actor lacks a permission."""

    def __init__(self, perm: str):
        self.perm = perm
        super().__init__(
            f"Not authorized: this action requires the '{perm}' permission.")


class PlatformAdminRequired(PermissionError):
    """Raised by require_platform() when a bound tenant actor tries a
    control-plane (cross-tenant) action."""

    def __init__(self):
        super().__init__(
            "Not authorized: this action is restricted to the platform "
            "operator.")


def set_actor_role(role: Optional[str]) -> None:
    """Bind the current actor's role (e.g. 'ADMIN'). None = system/unrestricted."""
    _actor_role.set(role)


def set_platform_admin(flag: bool) -> None:
    """Mark (or unmark) the current actor as the platform operator."""
    _platform_admin.set(bool(flag))


def set_request_context(flag: bool) -> None:
    """Mark (or unmark) the current context as an interactive request (web/API).
    When set, an unbound actor fails CLOSED (see has_perm)."""
    _request_context.set(bool(flag))


def is_platform_admin() -> bool:
    return _platform_admin.get()


def clear_actor() -> None:
    _actor_role.set(None)
    _platform_admin.set(False)
    _request_context.set(False)


def current_role() -> Optional[str]:
    return _actor_role.get()


def has_perm(perm: str) -> bool:
    role = _actor_role.get()
    if role is None:
        # No bound actor. Inside an interactive request this means the boundary
        # forgot to bind a role — fail CLOSED. Outside one (CLI, scheduled jobs,
        # seed, migrations, tests) keep the documented break-glass (fail-open).
        return not _request_context.get()
    from .models.users import PERMISSIONS, Role
    try:
        return perm in PERMISSIONS.get(Role(role), set())
    except ValueError:
        return False


def require_perm(perm: str) -> None:
    """Raise PermissionDenied if the current actor may not perform `perm`."""
    if not has_perm(perm):
        raise PermissionDenied(perm)


def require_platform() -> None:
    """Guard control-plane (cross-tenant) actions — creating/mutating tenants
    and API keys — at the SERVICE layer, so they are protected regardless of
    entry point (UI page, REST API, a future caller).

    Passes when:
      * the current session is an allow-listed platform operator
        (set_platform_admin(True) — only auth.require_login does this), OR
      * no interactive actor is bound at all (CLI, scheduled jobs, migrations,
        seed code, tests) — the documented break-glass / system context.

    Denies a bound *tenant* actor (a tenant-admin UI session or a tenant-scoped
    API key), which is exactly what stops one tenant from touching another.
    """
    if _platform_admin.get():
        return
    if _actor_role.get() is None and not _request_context.get():
        return   # system / CLI / scheduled / test — unrestricted break-glass
    raise PlatformAdminRequired()
