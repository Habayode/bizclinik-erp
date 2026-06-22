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

from . import authz


_PASSWORD_ENV = "BIZCLINIK_APP_PASSWORD"
_PLATFORM_ADMINS_ENV = "BIZCLINIK_PLATFORM_ADMINS"
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


def require_any_perm(perms, *, error: str = "You don't have permission to access this.") -> None:
    """Gate a page that serves several roles (e.g. Settings: company profile is
    admin, but customers/suppliers/banks belong to other roles). Allowed if the
    user holds ANY of `perms`."""
    if not any(has_perm(p) for p in perms):
        st.error(error)
        st.stop()


# ---- platform operator (manages ALL tenants, vs a tenant-level admin) ------


def _platform_principals() -> list[str]:
    """Allow-listed operator principals from BIZCLINIK_PLATFORM_ADMINS — comma
    separated, each either ``slug:username`` (the tenant the operator signs into
    + their username) or a bare ``username`` (only honoured in single-tenant
    mode). Empty when unset."""
    raw = os.environ.get(_PLATFORM_ADMINS_ENV, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def evaluate_platform_admin(*, principals: list[str], active_tenant: Optional[str],
                            username: Optional[str], role: Optional[str],
                            logged_in: bool, has_tenants: bool) -> bool:
    """Pure decision (no Streamlit) so it is unit-testable.

    Rules, designed so a tenant's bootstrap ``admin`` (which is handed to the
    client) can NEVER become a platform operator unless explicitly allow-listed
    under the operator's OWN tenant slug:

      * Allow-list set → operator iff a principal matches. ``slug:username`` must
        match BOTH the signed-into tenant and the username. Bare ``username``
        entries are honoured ONLY in single-tenant mode (no tenants registered),
        never when tenants exist.
      * Allow-list empty → in multi-tenant mode NOBODY is an operator (fail
        closed); in single-tenant/legacy mode the lone signed-in ADMIN is the
        operator (there is no registry to leak).
    """
    if not logged_in:
        return False
    if not principals:
        return (not has_tenants) and role == "ADMIN"
    for p in principals:
        if ":" in p:
            slug, uname = (x.strip() for x in p.split(":", 1))
            if slug and uname and active_tenant == slug and username == uname:
                return True
        elif (not has_tenants) and active_tenant is None and username == p:
            return True
    return False


def is_platform_admin() -> bool:
    """True only for the platform operator (manages all tenants) — never for an
    ordinary tenant admin. Evaluate only AFTER require_login()/_apply_tenant()
    has resolved the active tenant. See evaluate_platform_admin for the rules."""
    from . import tenancy
    u = current_user()
    if u:
        username, role, logged_in = u.get("username"), u.get("role"), True
    elif st.session_state.get(_LEGACY_KEY) and not _any_users_configured():
        # Legacy single-password mode: the implicit single user is admin.
        username, role, logged_in = "admin", "ADMIN", True
    else:
        username, role, logged_in = None, None, False
    try:
        has = tenancy.has_tenants()
    except Exception:
        has = False
    return evaluate_platform_admin(
        principals=_platform_principals(), active_tenant=active_tenant(),
        username=username, role=role, logged_in=logged_in, has_tenants=has)


def require_platform_admin(*, error: str = (
        "Platform operators only. This console manages every business on the "
        "platform and isn't available to individual tenant accounts.")) -> None:
    """Gate a control-plane page (e.g. Tenants). Stops before any cross-tenant
    data is read/rendered."""
    if not is_platform_admin():
        st.error(error)
        st.stop()


# ---- lock screen ----------------------------------------------------------


def _active_company():
    """(name, vertical) for the active tenant — used to brand the login card.
    Fails safe to (None, 'general')."""
    try:
        from .db import get_session
        from .models import Company
        with get_session() as s:
            co = s.query(Company).first()
            return (co.name, (co.vertical or "general")) if co else (None, "general")
    except Exception:
        return (None, "general")


def _render_brand_card() -> None:
    try:
        from . import ui_kit
        ui_kit.inject_brand()
    except Exception:
        pass
    # Pre-login screens stop before the custom st.navigation runs, so Streamlit
    # would otherwise show its raw auto-discovered page list in the sidebar.
    # Hide the sidebar entirely on the sign-in screens.
    st.markdown(
        "<style>section[data-testid='stSidebar']{display:none !important;}"
        "[data-testid='stSidebarNav']{display:none !important;}</style>",
        unsafe_allow_html=True)
    name, vertical = _active_company()
    if vertical == "school" and name:
        badge, title, subtitle = "🏫", name, "School portal · sign in to continue"
    else:
        badge, title, subtitle = "T3", "Trakit365 ERP", "Sign in to continue"
    st.markdown(
        "<div style='max-width: 380px; margin: 4rem auto 0 auto; "
        "background: white; border: 1px solid #E5E7EB; border-radius: 12px; "
        "padding: 28px 28px 24px 28px; box-shadow: 0 6px 20px rgba(15,23,42,0.06);'>"
        "<div style='display:flex; align-items:center; gap:10px; margin-bottom: 6px;'>"
        "<div style='width:36px; height:36px; border-radius:8px; "
        "background:#1F3864; color:white; display:flex; align-items:center; "
        f"justify-content:center; font-weight:700;'>{badge}</div>"
        f"<div><div style='font-weight:700; color:#0F172A;'>{title}</div>"
        f"<div style='font-size:0.8rem; color:#64748B;'>{subtitle}</div></div>"
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


def _slug_candidates(text: str) -> list[str]:
    """Derive tenant-slug candidates from whatever the user types — a bare ID
    (``otasch``), the ``-erp`` form (``otasch-erp``), or the full web address
    (``https://otasch-erp.hagai.online/Dashboard``). Returns ordered candidates
    to try against the registry; pure (no Streamlit) so it is unit-testable."""
    s = (text or "").strip().lower()
    if not s:
        return []
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0].split("?", 1)[0].split(":")[0].strip().rstrip(".")
    label = s.split(".", 1)[0] if "." in s else s   # leftmost DNS label
    out: list[str] = []
    for c in (label, label[:-4] if label.endswith("-erp") else None, s):
        if c and c not in out:
            out.append(c)
    return out


def _tenant_picker() -> None:
    """Pre-login business entry. We deliberately do NOT list registered
    businesses — a visitor must not be able to enumerate tenants. Each business
    signs in at its own web address (``<id>-erp.hagai.online``, which
    auto-selects the tenant); on the bare domain the user types their business
    ID or web address. st.stop()s until a valid, active business is chosen."""
    from . import tenancy
    _render_brand_card()
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown("#### Sign in to your business")
        with st.form("biz_entry"):
            entered = st.text_input(
                "Business ID or web address",
                placeholder="e.g. otasch  ·  or otasch-erp.hagai.online")
            go = st.form_submit_button("Continue", type="primary",
                                       use_container_width=True)
        if go:
            chosen = None
            for cand in _slug_candidates(entered):
                t = tenancy.get_tenant(cand)
                if t and t.get("is_active", True):
                    chosen = cand
                    break
            if chosen:
                st.session_state[_TENANT_KEY] = chosen
                # New tenant => drop any prior login state.
                for k in (_USER_KEY, _USERNAME_KEY, _ROLE_KEY, _TOKEN_KEY, _LEGACY_KEY):
                    st.session_state.pop(k, None)
                st.rerun()
            else:
                st.error("We couldn't find that business. Check the ID, or open "
                         "your business web address to sign in directly.")
        st.caption("Tip: open your business web address — e.g. "
                   "yourbusiness-erp.hagai.online — to sign in straight away.")

        st.divider()
        # New visitors are sent to the marketing site to request a demo (the
        # demo form lives there); the app login is only for existing businesses.
        st.markdown(
            "<p style='text-align:center;margin:0.25rem 0 0;'>New to Trakit365? "
            "<a href='https://trakit365.hagai.online' target='_blank' "
            "rel='noopener'>See what it does and request a demo &rarr;</a></p>",
            unsafe_allow_html=True)
    st.stop()


# Leftmost labels that are infrastructure, never a tenant slug.
_RESERVED_SUBDOMAINS = {"www", "erp", "api", "app", "admin", "mail",
                        "ftp", "cdn", "static", "ns1", "ns2"}


def _subdomain_from_request() -> Optional[str]:
    """Return the candidate tenant slug encoded in the request host, if any.

    Domain-agnostic: the *leftmost* DNS label is treated as the slug, unless it
    is a reserved infrastructure label. The caller still validates the slug
    against the tenant registry, so a non-tenant label simply falls through to
    the picker. This means both layouts resolve with no code change:

      • nested (current free TLS):   wendysrack.erp.hagai.online -> 'wendysrack'
      • flat (dedicated domain):     acme.bizclinik.app          -> 'acme'

    Returns None for apex hosts (``zone.tld``), ``localhost``, bare IPs, and
    reserved labels (``erp``/``api``/``www``/...).
    """
    try:
        headers = st.context.headers  # Streamlit >= 1.37
        host = (headers.get("host") or headers.get("Host") or "")
    except Exception:
        return None
    host = host.split(":")[0].strip().lower().rstrip(".")
    if not host:
        return None
    # Bare IPv4 address -> no subdomain.
    if host.replace(".", "").isdigit():
        return None
    parts = host.split(".")
    # Need at least <label>.<zone>.<tld> (3 labels) for a real subdomain.
    if len(parts) < 3:
        return None
    label = parts[0]
    if label in _RESERVED_SUBDOMAINS:
        return None
    return label


def _resolve_subdomain_slug() -> Optional[str]:
    """Map the request host's leftmost label to a registered tenant slug.

    Tries the label as-is, then with a trailing ``-erp`` stripped, so all of
    these resolve tenant ``acme`` without further config:

      • acme.example.com            (flat, dedicated domain — free TLS)
      • acme-erp.hagai.online       (one level under hagai.online — free TLS)
      • acme.erp.hagai.online       (nested — needs paid ACM, but still maps)

    Returns the matching slug, or None if no tenant matches.
    """
    from . import tenancy
    label = _subdomain_from_request()
    if not label:
        return None
    for cand in (label, label[:-4] if label.endswith("-erp") else None):
        if cand and tenancy.get_tenant(cand):
            return cand
    return None


def _apply_tenant() -> None:
    """Resolve + activate the tenant for this script run. No-op (legacy single
    DB) when no tenants are registered. A tenant subdomain auto-selects its
    tenant and skips the picker (see _resolve_subdomain_slug for the formats)."""
    from . import tenancy
    if not tenancy.has_tenants():
        tenancy.set_active(None)
        return

    # Subdomain auto-routing -> that tenant.
    if not st.session_state.get(_TENANT_KEY):
        slug = _resolve_subdomain_slug()
        if slug:
            st.session_state[_TENANT_KEY] = slug

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
        authz.set_request_context(True)   # configured auth -> unbound fails closed
        if st.session_state.get(_USER_KEY):
            # Bind the actor so service-layer authz enforces this user's role.
            authz.set_actor_role(st.session_state.get(_ROLE_KEY))
            authz.set_platform_admin(is_platform_admin())
            return
        authz.clear_actor()
        _user_login_screen()
        return

    if _expected_password() is None:
        return                       # dev: no auth configured -> unrestricted
    authz.set_request_context(True)  # configured auth -> unbound fails closed
    if st.session_state.get(_LEGACY_KEY):
        authz.set_actor_role("ADMIN")   # legacy single-password = implicit admin
        authz.set_platform_admin(is_platform_admin())
        return
    authz.clear_actor()
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
