"""Simple password gate for the Streamlit ERP.

Reads `BIZCLINIK_APP_PASSWORD` from the environment.
  - If unset → auth is disabled (local dev). The app loads normally.
  - If set   → every page calls `require_login()` first; until the user
               enters the matching password the page renders a lock screen
               and st.stop()s.

Session persistence: success is stored in st.session_state so subsequent
page navigations don't re-prompt. A logout button clears the session.

Brute-force guard: 5 failures lock the session for the rest of its lifetime.
This is a single-password gate, not a multi-user system — for that, swap in
streamlit-authenticator. Good enough for "share with one or two trusted
people behind a Cloudflare tunnel".
"""
from __future__ import annotations

import hmac
import os

import streamlit as st


_PASSWORD_ENV = "BIZCLINIK_APP_PASSWORD"
_SESSION_KEY = "_bizclinik_authed"
_FAIL_KEY = "_bizclinik_login_fails"
_MAX_FAILS = 5


def _expected_password() -> str | None:
    pw = os.environ.get(_PASSWORD_ENV, "").strip()
    return pw or None


def _attempt_login(submitted: str) -> bool:
    expected = _expected_password()
    if not expected:
        return True
    # Constant-time compare prevents trivial timing leaks.
    return hmac.compare_digest(submitted, expected)


def _lock_screen() -> None:
    """Render the lock screen + handle the form submission."""
    # Centre the form. Use brand styling if ui_kit is available.
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

    # Place the form within the same visual column for layout symmetry.
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
            if _attempt_login(pw):
                st.session_state[_SESSION_KEY] = True
                st.session_state[_FAIL_KEY] = 0
                st.rerun()
            else:
                st.session_state[_FAIL_KEY] = fails + 1
                left = _MAX_FAILS - st.session_state[_FAIL_KEY]
                st.error(f"Wrong password. {left} attempt(s) left this session.")
    st.stop()


def require_login() -> None:
    """Call at the top of every page (after `st.set_page_config`). Renders
    the lock screen and st.stop()s if not logged in. No-op when password is
    unset in the environment."""
    if _expected_password() is None:
        return
    if st.session_state.get(_SESSION_KEY):
        return
    _lock_screen()


def render_logout_in_sidebar() -> None:
    """Place a small logout button in the sidebar. Call after require_login()."""
    if _expected_password() is None:
        return
    with st.sidebar:
        st.divider()
        if st.button("Sign out", width="stretch"):
            st.session_state.pop(_SESSION_KEY, None)
            st.session_state.pop(_FAIL_KEY, None)
            st.rerun()
