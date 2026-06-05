"""Emailing a customer statement PDF (SMTP send stubbed)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select


def _seed_customer(s, email="client@example.com"):
    from bizclinik_erp.models import Customer
    c = Customer(code="C1", name="Acme Ltd", email=email)
    s.add(c)
    s.flush()
    return c.id


def test_email_statement_no_recipient(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import customer_statement as cs
    with get_session() as s:
        cid = _seed_customer(s, email=None)
    with get_session() as s:
        res = cs.email_statement(s, cid, period_start=date(2026, 1, 1),
                                 period_end=date(2026, 1, 31))
        assert res["sent"] is False
        assert "No email" in res["reason"]


def test_email_statement_smtp_not_configured(fresh_db, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import customer_statement as cs
    with get_session() as s:
        cid = _seed_customer(s)
    with get_session() as s:
        res = cs.email_statement(s, cid, period_start=date(2026, 1, 1),
                                 period_end=date(2026, 1, 31))
        assert res["sent"] is False
        assert "SMTP" in res["reason"]


def test_email_statement_sends_with_attachment(fresh_db, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import customer_statement as cs
    from bizclinik_erp.services import notifications

    captured = {}

    def fake_send(*, to_addr, subject, body_text, attachment_path=None,
                  attachment_name=None, body_html=None):
        from pathlib import Path
        captured["to"] = to_addr
        captured["subject"] = subject
        # The PDF must exist at send time and be a real PDF.
        assert attachment_path and Path(attachment_path).exists()
        assert Path(attachment_path).read_bytes()[:4] == b"%PDF"
        captured["attached"] = attachment_name
        return True

    monkeypatch.setattr(notifications, "send_email_with_attachment", fake_send)

    with get_session() as s:
        cid = _seed_customer(s)
    with get_session() as s:
        res = cs.email_statement(s, cid, period_start=date(2026, 1, 1),
                                 period_end=date(2026, 1, 31),
                                 to_addr="override@example.com")
    assert res["sent"] is True
    assert captured["to"] == "override@example.com"
    assert captured["attached"].endswith(".pdf")
    assert "Statement of Account" in captured["subject"]
