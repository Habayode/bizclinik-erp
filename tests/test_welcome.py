"""The JARVIS-style login welcome — pure text/HTML building and best-effort
briefing (must never raise)."""
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


def test_spoken_and_subline():
    spk = welcome.spoken_text("Good evening", "Olubayode", [])
    assert "Olubayode" in spk and "Trakit365" in spk
    assert welcome.subline([]).endswith("Everything is in order.")
    sub = welcome.subline(["3 approvals awaiting a decision"])
    assert "3 approvals" in sub


def test_build_html_has_no_leftover_placeholders():
    doc = welcome.build_html("Good evening, Ada", "Welcome back.", "Good evening, Ada.")
    assert "__SUB__" not in doc
    assert "__HEAD__" not in doc
    assert "__SPK__" not in doc
    assert "speechSynthesis" in doc           # speaks aloud
    assert "Good evening, Ada" in doc          # JS-embedded headline


def test_build_briefing_never_raises(fresh_db):
    from bizclinik_erp.db import get_session
    with get_session() as s:
        lines = welcome.build_briefing(s, {"username": "admin"})
    assert isinstance(lines, list)  # empty on a fresh book, but always a list
