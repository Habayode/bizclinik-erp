"""Parent notifications: provider-agnostic SMS (log default), fee reminders,
recipient/SMTP handling, and bulk-to-defaulters — all GL-free."""
from __future__ import annotations

from datetime import date

import pytest


def _billed_student(s, *, with_phone=True, with_email=False, pay=0.0):
    """Set up education COA + a fee + class + session + an enrolled, billed
    student. Returns (student_id, billing)."""
    from bizclinik_erp.services import school, school_enrol, school_billing, coa_templates
    coa_templates.apply_template(s, "education")
    sess = school.create_academic_session(s, session_code="2025/2026", make_current=True)
    cls = school.create_school_class(s, class_code="JSS1A", name="JSS1A")
    ft = school.create_fee_type(s, code="TUI", name="Tuition", income_account_code="4400")
    school.set_fee_schedule(s, academic_session_id=sess.id, fee_type_id=ft.id,
                            class_id=cls.id, term_number=1, amount=50000)
    stu = school_enrol.enrol_student(
        s, first_name="Ada", last_name="Okeke", class_id=cls.id,
        academic_session_id=sess.id,
        guardian_name="Mrs Okeke",
        guardian_phone="08030001111" if with_phone else None,
        guardian_email="okeke@mail.ng" if with_email else None)
    b = school_billing.bill_student(s, student_id=stu.id, academic_session_id=sess.id,
                                    term_number=1, invoice_date=date(2025, 9, 15))
    if pay:
        from sqlalchemy import select
        from bizclinik_erp.models import BankAccount
        bank = s.execute(select(BankAccount.id)).scalars().first()
        school_billing.record_fee_payment(s, student_id=stu.id, sales_invoice_id=b.sales_invoice_id,
                                          amount=pay, payment_date=date(2025, 9, 20),
                                          bank_account_id=bank)
    return stu.id, b


def test_default_sms_provider_is_log():
    from bizclinik_erp.services import sms
    p = sms.get_sms_provider()
    assert p.name == "log" and p.configured()
    r = p.send(to="08030001111", message="hi")
    assert r.ok and r.transmitted is False


def test_fee_reminder_sms_logged(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_notify
    from bizclinik_erp.models import NotifyStatus, NotifyKind, NotifyChannel
    with get_session() as s:
        sid, _ = _billed_student(s, with_phone=True)
        n = school_notify.send_fee_reminder(s, student_id=sid, channel="SMS")
        assert n.status == NotifyStatus.LOGGED      # log provider records, no gateway
        assert n.kind == NotifyKind.FEE_REMINDER and n.channel == NotifyChannel.SMS
        assert n.recipient == "08030001111" and "50,000" in n.body


def test_fee_reminder_skips_when_paid(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_notify
    with get_session() as s:
        sid, _ = _billed_student(s, with_phone=True, pay=50000)
        assert school_notify.send_fee_reminder(s, student_id=sid, channel="SMS") is None


def test_sms_reminder_no_phone_fails(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_notify
    from bizclinik_erp.models import NotifyStatus
    with get_session() as s:
        sid, _ = _billed_student(s, with_phone=False)
        n = school_notify.send_fee_reminder(s, student_id=sid, channel="SMS")
        assert n.status == NotifyStatus.FAILED and "phone" in n.error.lower()


def test_email_reminder_without_smtp_fails_clean(fresh_db, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_notify
    from bizclinik_erp.models import NotifyStatus
    with get_session() as s:
        sid, _ = _billed_student(s, with_email=True)
        n = school_notify.send_fee_reminder(s, student_id=sid, channel="EMAIL")
        assert n.status == NotifyStatus.FAILED and "SMTP" in (n.error or "")


def test_bulk_reminders_tally(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_notify
    with get_session() as s:
        _billed_student(s, with_phone=True)        # one defaulter
        tally = school_notify.bulk_fee_reminders(s, channel="SMS")
        assert tally["logged"] == 1 and tally["sent"] == 0 and tally["failed"] == 0
