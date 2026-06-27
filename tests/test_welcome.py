"""The JARVIS-style login welcome — pure text/HTML building, best-effort
briefing (must never raise), and per-user show/voice preferences."""
from __future__ import annotations

from bizclinik_erp import welcome


def test_time_greeting_buckets():
    assert welcome.time_greeting(8) == "Good morning"
    assert welcome.time_greeting(13) == "Good afternoon"
    assert welcome.time_greeting(20) == "Good evening"
    assert welcome.time_greeting(2) == "Good evening"


def test_display_name_from_username():
    assert welcome.display_name({"username": "olubayode.okubanjo"}) == "Olubayode"
    assert welcome.display_name({"username": "jane@sunrise.edu"}) == "Jane"
    assert welcome.display_name({"full_name": "grace"}) == "Grace"
    assert welcome.display_name({}) == "there"


def test_brief_clause_variants():
    assert welcome.brief_clause(None, []) == "All quiet on the books."
    assert welcome.brief_clause("₦1.2m in revenue", []) == "₦1.2m in revenue."
    assert "You have 2 approvals" in welcome.brief_clause(None, ["2 approvals await"])
    both = welcome.brief_clause("₦1.2m in revenue", ["2 approvals await"])
    assert "₦1.2m" in both and "You have" in both


def test_assemble_butler_tone():
    sub, spoken = welcome.assemble("Good evening", "Olubayode", "All quiet on the books.")
    assert "Trakit365 at your service" in sub and "Shall we begin?" in sub
    assert "Olubayode" in spoken and "All systems are online" in spoken


def test_build_html_voice_on_and_off():
    on = welcome.build_html("Trakit365 • Assistant · Fri 27 Jun 2026",
                            "Good evening, Ada.", "Welcome.", "Good evening, Ada.",
                            voice=True)
    for tok in ("__SUB__", "__HEAD__", "__SPK__", "__KIC__", "__REPLAY__", "__VOICEJS__"):
        assert tok not in on
    assert "SpeechSynthesisUtterance" in on and "Replay" in on  # speaks aloud
    assert "Fri 27 Jun 2026" in on            # date shown in the kicker

    off = welcome.build_html("k", "Good evening, Ada.", "Welcome.", "spoken",
                             voice=False)
    assert "SpeechSynthesisUtterance" not in off and "Replay" not in off
    assert "__VOICEJS__" not in off


def test_build_briefing_and_kpi_never_raise(fresh_db):
    from bizclinik_erp.db import get_session
    with get_session() as s:
        assert isinstance(welcome.build_briefing(s, {"username": "admin"}), list)
        assert welcome.kpi_line(s) in (None,) or isinstance(welcome.kpi_line(s), str)


def test_welcome_prefs_roundtrip(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.users import (
        create_user, get_welcome_prefs, set_welcome_prefs)

    with get_session() as s:
        u = create_user(s, username="bursar", password="pw")
        uid = u.id
    # default is on/on
    with get_session() as s:
        assert get_welcome_prefs(s, uid) == (True, True)
    # mute the voice, keep the banner
    with get_session() as s:
        set_welcome_prefs(s, uid, show=True, voice=False)
    with get_session() as s:
        assert get_welcome_prefs(s, uid) == (True, False)
    # missing user -> safe default
    with get_session() as s:
        assert get_welcome_prefs(s, 999999) == (True, True)
