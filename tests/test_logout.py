"""The sign-out control must render exactly once per run, and must be present
even when the page body early-stops (the bug: the operator's company-setup
screen st.stop()'d before its own bottom-of-page call)."""
from __future__ import annotations

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest


_LOGGED_IN = """
import streamlit as st
from bizclinik_erp import auth
auth._any_users_configured = lambda: True          # pretend users exist
st.session_state["_bizclinik_user_id"] = 1
st.session_state["_bizclinik_username"] = "operator"
st.session_state["_bizclinik_role"] = "ADMIN"
"""


def _signout_buttons(at):
    return [b for b in at.sidebar.button if b.label == "Sign out"]


def test_global_then_per_page_renders_once():
    """Home.py renders it (force=True); the page's own call then no-ops."""
    script = _LOGGED_IN + (
        "auth.render_logout_in_sidebar(force=True)\n"   # Home.py (global)
        "st.stop()  # simulate the page body early-stopping\n"
        "auth.render_logout_in_sidebar()  # never reached, but proves no double\n"
    )
    at = AppTest.from_string(script).run()
    assert len(_signout_buttons(at)) == 1


def test_present_even_when_page_early_stops():
    """Even if the page stops immediately, the global render already happened."""
    script = _LOGGED_IN + (
        "auth.render_logout_in_sidebar(force=True)\n"
        "st.stop()\n"
    )
    at = AppTest.from_string(script).run()
    assert len(_signout_buttons(at)) == 1


def test_two_plain_calls_still_render_once():
    """Belt-and-suspenders: two per-page calls in one run don't double up."""
    script = _LOGGED_IN + (
        "auth.render_logout_in_sidebar()\n"
        "auth.render_logout_in_sidebar()\n"
    )
    at = AppTest.from_string(script).run()
    assert len(_signout_buttons(at)) == 1
