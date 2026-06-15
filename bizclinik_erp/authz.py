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


class PermissionDenied(PermissionError):
    """Raised by require_perm() when the current actor lacks a permission."""

    def __init__(self, perm: str):
        self.perm = perm
        super().__init__(
            f"Not authorized: this action requires the '{perm}' permission.")


def set_actor_role(role: Optional[str]) -> None:
    """Bind the current actor's role (e.g. 'ADMIN'). None = system/unrestricted."""
    _actor_role.set(role)


def clear_actor() -> None:
    _actor_role.set(None)


def current_role() -> Optional[str]:
    return _actor_role.get()


def has_perm(perm: str) -> bool:
    role = _actor_role.get()
    if role is None:
        return True   # system / CLI / scheduled / test context — unrestricted
    from .models.users import PERMISSIONS, Role
    try:
        return perm in PERMISSIONS.get(Role(role), set())
    except ValueError:
        return False


def require_perm(perm: str) -> None:
    """Raise PermissionDenied if the current actor may not perform `perm`."""
    if not has_perm(perm):
        raise PermissionDenied(perm)
