"""The public demo-request endpoint emails the operator (best-effort) when a
lead arrives. The send is gated on DEMO_REQUEST_EMAIL + a configured transport
(Resend HTTP API, preferred, or SMTP fallback), runs in the background, and
never breaks lead capture. It also sets Reply-To to the prospect so the
operator can reply directly."""
from __future__ import annotations

import inspect

from api.main import DemoIn, _notify_demo_lead
from bizclinik_erp.services import notifications


def test_send_message_accepts_reply_to():
    params = inspect.signature(notifications.send_message).parameters
    assert "reply_to" in params


def test_resend_preferred_over_smtp(monkeypatch):
    """When RESEND_API_KEY is set, send_message uses the Resend HTTP path and
    never touches SMTP."""
    calls = {"resend": 0, "smtp": 0}
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(notifications, "_send_via_resend",
                        lambda **k: (calls.__setitem__("resend", calls["resend"] + 1) or True))
    monkeypatch.setattr(notifications, "send_email_with_attachment",
                        lambda **k: (calls.__setitem__("smtp", calls["smtp"] + 1) or True))
    notifications.send_message(to_addr="a@b.com", subject="x", body_text="y")
    assert calls == {"resend": 1, "smtp": 0}


def test_notify_skips_without_recipient(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "send_message",
                        lambda **k: (calls.append(k) or True))
    monkeypatch.delenv("DEMO_REQUEST_EMAIL", raising=False)
    _notify_demo_lead(DemoIn(name="A", email="a@b.com"))
    assert calls == []


def test_notify_skips_when_no_transport(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "send_message",
                        lambda **k: (calls.append(k) or True))
    monkeypatch.setattr(notifications, "email_configured", lambda: False)
    monkeypatch.setenv("DEMO_REQUEST_EMAIL", "ops@example.com")
    _notify_demo_lead(DemoIn(name="A", email="a@b.com"))
    assert calls == []


def test_notify_sends_with_reply_to(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "send_message",
                        lambda **k: (calls.append(k) or True))
    monkeypatch.setattr(notifications, "email_configured", lambda: True)
    monkeypatch.setenv("DEMO_REQUEST_EMAIL", "ops@example.com")
    _notify_demo_lead(DemoIn(name="Jane Bursar", business="Sunrise School",
                             email="jane@sunrise.edu", phone="08000000000",
                             message="Interested in the school edition"))
    assert len(calls) == 1
    k = calls[0]
    assert k["to_addr"] == "ops@example.com"
    assert k["reply_to"] == "jane@sunrise.edu"
    assert "Jane Bursar" in k["subject"] and "Sunrise School" in k["subject"]
    assert "jane@sunrise.edu" in k["body_text"]
    assert "Interested in the school edition" in k["body_text"]
