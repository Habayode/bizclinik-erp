"""Authentication for the Streamlit ERP.

Two modes, chosen automatically:

  • Single-password (legacy) — when `BIZCLINIK_APP_PASSWORD` is set and no
    `User` rows exist yet. Backwards-compatible with the original deploy.

  • Multi-user — once any `User` row exists in the DB, the lock screen asks
    for username + password. Logged-in user is stored in `st.session_state`
    and exposed via `current_user()`. Use `require_perm("...")` to gate UI
    blocks per role.

A bootstrap admin is auto-created on first login attempt using the env-var
password as the admin password, so the first sign-in transparently becomes
the admin account.
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

import streamlit as st


_PASSWORD_ENV = "BIZCLINIK_APP_PASSWORD"
_LEGACY_KEY = "_bizclinik_authed"
_USER_KEY = "_bizclinik_user_id"
_USERNAME_KEY = "_bizclinik_username"
_ROLE_KEY = "_bizclinik_role"
_TOKEN_KEY = "_bizclinik_session_token"
_FAIL_KEY = "_bizclinik_login_fails"
_MAX_FAILS = 5


# ---- helpers --------------------------------------------------------------


def _expected_password() -> str | None:
    pw = os.environ.get(_PASSWORD_ENV, "").strip()
    return pw or None


def _any_users_configured() -> bool:
    """Returns True if at least one User row exists. Cached for the session."""
    try:
        from .db import get_session
        from .models.users import User
        with get_session() as s:
            return s.query(User).first() is not None
    except Exception:
        return False


def current_user() -> Optional[dict]:
    """Return {user_id, username, role} for the logged-in user, or None."""
    if not st.session_state.get(_USER_KEY):
        return None
    return {
        "user_id": st.session_state.get(_USER_KEY),
        "username": st.session_state.get(_USERNAME_KEY),
        "role": st.session_state.get(_ROLE_KEY),
    }


def current_user_id() -> Optional[int]:
    return st.session_state.get(_USER_KEY)


def has_perm(perm: str) -> bool:
    """True if the logged-in user has `perm`. Legacy single-password mode
    always returns True (single user is implicit admin)."""
    if not _any_users_configured():
        # Single-password legacy mode — treat as admin.
        return st.session_state.get(_LEGACY_KEY, False) is True
    from .models.users import PERMISSIONS, Role
    role_str = st.session_state.get(_ROLE_KEY)
    if not role_str:
        return False
    try:
        return perm in PERMISSIONS.get(Role(role_str), set())
    except ValueError:
        return False


def require_perm(perm: str, *, error: str = "You don't have permission to access this.") -> None:
    if not has_perm(perm):
        st.error(error)
        st.stop()


# ---- lock screen ----------------------------------------------------------


def _render_brand_card() -> None:
    try:
        from . import ui_kit
        ui_kit.inject_brand()
    except Exception:
        pass
    st.markdown(
        "<div style='max-width: 380px; margin: 4rem auto 0 auto; "
        "background: white; border: 1px solid #E5E7EB; border-radius: 12px; "
        "padding: 28px 28px 24px 28px; box-shadow: 0 6px 20px rgba(15,23,42,0.06);'>"
        "<div style='display:flex; align-items:center; gap:10px; margin-bottom: 6px;'>"
        "<div style='width:36px; height:36px; border-radius:8px; "
        "background:#1F3864; color:white; display:flex; align-items:center; "
        "justify-content:center; font-weight:700;'>BC</div>"
        "<div><div style='font-weight:700; color:#0F172A;'>BizClinik ERP</div>"
        "<div style='font-size:0.8rem; color:#64748B;'>Sign in to continue</div></div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _user_login_screen() -> None:
    _render_brand_card()
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        fails = st.session_state.get(_FAIL_KEY, 0)
        if fails >= _MAX_FAILS:
            st.error("Too many failed attempts. Restart the session to retry.")
            st.stop()
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", autocomplete="username")
            pw = st.text_input("Password", type="password", autocomplete="current-password")
            submit = st.form_submit_button("Sign in", type="primary",
                                             use_container_width=True)
        if submit:
            from .db import get_session
            from .services.users import authenticate
            with get_session() as s:
                user_session = authenticate(s, username, pw)
                if user_session:
                    user = user_session.user
                    st.session_state[_USER_KEY] = user.id
                    st.session_state[_USERNAME_KEY] = user.username
                    st.session_state[_ROLE_KEY] = user.role.value
                    st.session_state[_TOKEN_KEY] = user_session.token
                    st.session_state[_FAIL_KEY] = 0
                    # Legacy flag kept True so has_perm() works for callers that haven't migrated.
                    st.session_state[_LEGACY_KEY] = True
                    st.rerun()
                else:
                    st.session_state[_FAIL_KEY] = fails + 1
                    left = _MAX_FAILS - st.session_state[_FAIL_KEY]
                    st.error(f"Wrong username or password. {left} attempt(s) left this session.")
    st.stop()


def _legacy_password_screen() -> None:
    _render_brand_card()
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        fails = st.session_state.get(_FAIL_KEY, 0)
        if fails >= _MAX_FAILS:
            st.error("Too many failed attempts. Restart the session to retry.")
            st.stop()
        with st.form("login_form", clear_on_submit=False):
            pw = st.text_input("Password", type="password", autocomplete="current-password")
            submit = st.form_submit_button("Sign in", type="primary",
                                             use_container_width=True)
        if submit:
            expected = _expected_password() or ""
            if expected and hmac.compare_digest(pw, expected):
                st.session_state[_LEGACY_KEY] = True
                st.session_state[_FAIL_KEY] = 0
                st.rerun()
            else:
                st.session_state[_FAIL_KEY] = fails + 1
                left = _MAX_FAILS - st.session_state[_FAIL_KEY]
                st.error(f"Wrong password. {left} attempt(s) left this session.")
    st.stop()


# ---- public API -----------------------------------------------------------


_TENANT_KEY = "_bizclinik_tenant"


def active_tenant() -> Optional[str]:
    return st.session_state.get(_TENANT_KEY)


def _tenant_picker() -> None:
    """Render the business/tenant chooser before login. st.stop()s until one
    is selected. Only shown when >= 1 tenant is registered."""
    from . import tenancy
    _render_brand_card()
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown("#### Choose a business")
        tenants = tenancy.list_tenants()
        labels = {f"{t['name']}  ·  {t['slug']}": t["slug"] for t in tenants}
        sel = st.selectbox("Business", list(labels.keys()))
        if st.button("Continue", type="primary", use_container_width=True):
            st.session_state[_TENANT_KEY] = labels[sel]
            # New tenant => drop any prior login state.
            for k in (_USER_KEY, _USERNAME_KEY, _ROLE_KEY, _TOKEN_KEY, _LEGACY_KEY):
                st.session_state.pop(k, None)
            st.rerun()
    st.stop()


def _apply_tenant() -> None:
    """Resolve + activate the tenant for this script run. No-op (legacy single
    DB) when no tenants are registered."""
    from . import tenancy
    if not tenancy.has_tenants():
        tenancy.set_active(None)
        return
    sel = st.session_state.get(_TENANT_KEY)
    if not sel:
        _tenant_picker()  # st.stop() inside
        return
    tenancy.set_active(sel)


def require_login() -> None:
    """Top of every page. Picks a tenant (if multi-tenant), then renders the
    lock screen + st.stop() until signed in.

    Modes, transparent to the page:
      • Multi-tenant (>= 1 tenant registered) → tenant picker, then per-tenant
        username + password.
      • Single-tenant with users → username + password.
      • Single-tenant, BIZCLINIK_APP_PASSWORD set → legacy single-password.
      • Otherwise (dev) → no-op.
    """
    _apply_tenant()

    if _any_users_configured():
        if st.session_state.get(_USER_KEY):
            return
        _user_login_screen()
        return

    if _expected_password() is None:
        return
    if st.session_state.get(_LEGACY_KEY):
        return
    _legacy_password_screen()


def render_logout_in_sidebar() -> None:
    if not (_any_users_configured() or _expected_password()):
        return
    with st.sidebar:
        st.divider()
        u = current_user()
        if u:
            st.markdown(
                f"<div style='font-size:0.78rem; color:#CBD5E1; "
                f"padding: 0 8px;'>Signed in as <b>{u['username']}</b><br>"
                f"<span style='color:#94A3B8'>{u['role']}</span></div>",
                unsafe_allow_html=True,
            )
        if st.button("Sign out", width="stretch"):
            token = st.session_state.get(_TOKEN_KEY)
            if token:
                try:
                    from .db import get_session
                    from .services.users import logout
                    with get_session() as s:
                        logout(s, token)
                except Exception:
                    pass
            for k in (_LEGACY_KEY, _USER_KEY, _USERNAME_KEY, _ROLE_KEY,
                       _TOKEN_KEY, _FAIL_KEY, _TENANT_KEY):
                st.session_state.pop(k, None)
            st.rerun()
