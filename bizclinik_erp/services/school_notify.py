"""Parent notifications — fee reminders and statements to guardians by SMS/email.

Operational only (no GL impact). SMS goes through the provider-agnostic
``services.sms`` (default ``log`` records without sending, so it is demo-safe
and costs nothing until a real gateway is configured). Email reuses the existing
SMTP helper and the customer-statement emailer. Every attempt is recorded as a
ParentNotification row for an audit trail.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (Company, NotifyChannel, NotifyKind, NotifyStatus,
                      ParentNotification, Student)
from . import notifications as _email
from . import school_billing, sms


def _school_name(session: Session) -> str:
    co = session.query(Company).first()
    return (co.name if co and co.name else "the school")


def _student_name(stu: Student) -> str:
    return f"{stu.first_name} {stu.last_name}".strip()


def _chan(channel: Union[NotifyChannel, str]) -> NotifyChannel:
    return channel if isinstance(channel, NotifyChannel) else NotifyChannel(str(channel).upper())


def _reminder_message(guardian: str, student_name: str, school: str,
                      outstanding: float, channel: NotifyChannel) -> tuple:
    if channel == NotifyChannel.EMAIL:
        subject = f"{school} — Outstanding School Fees"
        body = (f"Dear {guardian},\n\nThis is a reminder that {student_name}'s "
                f"school fees at {school} currently show an outstanding balance "
                f"of NGN {outstanding:,.2f}.\n\nKindly arrange payment at your "
                f"earliest convenience. Thank you.\n\n{school}")
    else:  # SMS — short, ASCII
        subject = "Fee reminder"
        body = (f"Dear {guardian}, {student_name}'s fees at {school} have an "
                f"outstanding balance of NGN {outstanding:,.0f}. Kindly pay. Thank you.")
    return subject, body


def _record(session: Session, *, student_id, channel, kind, recipient, subject,
            body, status, provider=None, provider_ref=None, error=None) -> ParentNotification:
    n = ParentNotification(
        student_id=student_id, channel=channel, kind=kind, recipient=recipient,
        subject=subject, body=body, status=status, provider=provider,
        provider_ref=provider_ref, error=error,
        sent_at=(datetime.utcnow() if status in (NotifyStatus.SENT,
                                                 NotifyStatus.LOGGED) else None))
    session.add(n)
    session.flush()
    return n


def _send_text(session: Session, *, student: Student, channel: NotifyChannel,
               kind: NotifyKind, subject: str, body: str) -> ParentNotification:
    """Dispatch a text message on the chosen channel and log the outcome."""
    if channel == NotifyChannel.SMS:
        recipient = (student.guardian_phone or "").strip()
        if not recipient:
            return _record(session, student_id=student.id, channel=channel, kind=kind,
                           recipient=None, subject=subject, body=body,
                           status=NotifyStatus.FAILED, error="No guardian phone on file.")
        prov = sms.get_sms_provider()
        res = prov.send(to=recipient, message=body)
        if not res.ok:
            status = NotifyStatus.FAILED
        elif not res.transmitted:
            status = NotifyStatus.LOGGED   # log provider — recorded, not sent
        else:
            status = NotifyStatus.SENT
        return _record(session, student_id=student.id, channel=channel, kind=kind,
                       recipient=recipient, subject=subject, body=body, status=status,
                       provider=res.provider, provider_ref=res.ref, error=res.error)
    # EMAIL
    recipient = (student.guardian_email or "").strip()
    if not recipient:
        return _record(session, student_id=student.id, channel=channel, kind=kind,
                       recipient=None, subject=subject, body=body,
                       status=NotifyStatus.FAILED, error="No guardian email on file.")
    if not _email.smtp_configured():
        return _record(session, student_id=student.id, channel=channel, kind=kind,
                       recipient=recipient, subject=subject, body=body,
                       status=NotifyStatus.FAILED, provider="smtp",
                       error="SMTP not configured (set SMTP_HOST/USER/PASS/FROM).")
    ok = _email.send_email_with_attachment(to_addr=recipient, subject=subject, body_text=body)
    return _record(session, student_id=student.id, channel=channel, kind=kind,
                   recipient=recipient, subject=subject, body=body,
                   status=(NotifyStatus.SENT if ok else NotifyStatus.FAILED),
                   provider="smtp", error=None if ok else "SMTP send failed.")


def send_fee_reminder(session: Session, *, student_id: int,
                      channel: Union[NotifyChannel, str] = "SMS") -> Optional[ParentNotification]:
    """Send (or log) a fee reminder to a student's guardian. Returns None if the
    student has nothing outstanding."""
    authz.require_perm("manage.school")
    channel = _chan(channel)
    stu = session.get(Student, student_id)
    if stu is None:
        raise ValueError("Student not found.")
    bal = school_billing.student_balance(session, student_id)
    if bal["outstanding"] < 0.01:
        return None
    subject, body = _reminder_message(
        stu.guardian_name or "Parent/Guardian", _student_name(stu),
        _school_name(session), bal["outstanding"], channel)
    return _send_text(session, student=stu, channel=channel,
                      kind=NotifyKind.FEE_REMINDER, subject=subject, body=body)


def bulk_fee_reminders(session: Session, *,
                       channel: Union[NotifyChannel, str] = "SMS",
                       min_outstanding: float = 0.01) -> dict:
    """Send a fee reminder to every active student with an outstanding balance."""
    authz.require_perm("manage.school")
    channel = _chan(channel)
    students = session.execute(
        select(Student).where(Student.is_active == True)).scalars().all()  # noqa: E712
    tally = {"sent": 0, "logged": 0, "failed": 0, "skipped": 0}
    for stu in students:
        if school_billing.student_balance(session, stu.id)["outstanding"] < min_outstanding:
            tally["skipped"] += 1
            continue
        n = send_fee_reminder(session, student_id=stu.id, channel=channel)
        if n is None:
            tally["skipped"] += 1
        elif n.status == NotifyStatus.SENT:
            tally["sent"] += 1
        elif n.status == NotifyStatus.LOGGED:
            tally["logged"] += 1
        else:
            tally["failed"] += 1
    return tally


def send_statement_email(session: Session, *, student_id: int,
                         period_start: date, period_end: date) -> ParentNotification:
    """Email the student's fee statement PDF to the guardian (reuses the
    customer-statement emailer) and log it."""
    authz.require_perm("manage.school")
    from . import customer_statement
    stu = session.get(Student, student_id)
    if stu is None:
        raise ValueError("Student not found.")
    to_addr = (stu.guardian_email or "").strip() or None
    res = customer_statement.email_statement(
        session, stu.customer_id, period_start=period_start,
        period_end=period_end, to_addr=to_addr)
    sent = bool(res.get("sent"))
    return _record(session, student_id=stu.id, channel=NotifyChannel.EMAIL,
                   kind=NotifyKind.STATEMENT, recipient=res.get("to") or to_addr,
                   subject=f"{_school_name(session)} — Fee Statement",
                   body=f"Statement for {period_start} to {period_end}.",
                   status=(NotifyStatus.SENT if sent else NotifyStatus.FAILED),
                   provider="smtp", error=None if sent else res.get("reason"))


def send_custom(session: Session, *, student_id: int,
                channel: Union[NotifyChannel, str], subject: str,
                body: str) -> ParentNotification:
    authz.require_perm("manage.school")
    channel = _chan(channel)
    stu = session.get(Student, student_id)
    if stu is None:
        raise ValueError("Student not found.")
    if not (body or "").strip():
        raise ValueError("Message body is required.")
    return _send_text(session, student=stu, channel=channel,
                      kind=NotifyKind.CUSTOM, subject=(subject or "Message"), body=body)


def list_notifications(session: Session, limit: int = 200) -> list[ParentNotification]:
    return session.execute(
        select(ParentNotification).order_by(ParentNotification.id.desc())
        .limit(limit)).scalars().all()
