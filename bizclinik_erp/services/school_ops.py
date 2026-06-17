"""School service — Phase 4: attendance and academic results (GL-free).

Pure operational records — nothing here posts to the GL or touches the sales
engine. Attendance marks a student's daily presence per class; results capture
per-subject, per-term scores (CA + exam -> total -> grade). Read-only helpers
roll these up into a daily attendance summary and a term report card. Mutating
calls require the ``manage.school`` permission (enforced here so both the UI and
any future API are covered).
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (Attendance, AttendanceStatus, SchoolClass, Student,
                      StudentResult)


# --------------------------------------------------------------------------- #
# Attendance                                                                  #
# --------------------------------------------------------------------------- #

def record_attendance(session: Session, *, student_id: int, class_id: int,
                      attendance_date: date,
                      status: Union[AttendanceStatus, str],
                      marked_by_employee_id: Optional[int] = None,
                      remarks: Optional[str] = None) -> Attendance:
    """Record one student's attendance mark for a class on a day."""
    authz.require_perm("manage.school")
    if session.get(Student, student_id) is None:
        raise ValueError("Student not found.")
    if session.get(SchoolClass, class_id) is None:
        raise ValueError("Class not found.")
    if attendance_date is None:
        raise ValueError("attendance_date is required.")
    if not isinstance(status, AttendanceStatus):
        try:
            status = AttendanceStatus(str(status).strip().upper())
        except ValueError:
            raise ValueError(f"Invalid attendance status {status!r}.")
    obj = Attendance(student_id=student_id, class_id=class_id,
                     attendance_date=attendance_date, status=status,
                     marked_by_employee_id=marked_by_employee_id,
                     remarks=(remarks or None))
    session.add(obj); session.flush()
    return obj


def attendance_summary(session: Session, class_id: int,
                       attendance_date: date) -> dict:
    """Read-only counts of attendance marks for a class on one day."""
    rows = session.execute(select(Attendance).where(
        Attendance.class_id == class_id,
        Attendance.attendance_date == attendance_date)).scalars().all()
    out = {"present": 0, "absent": 0, "late": 0, "excused": 0, "total": 0}
    for r in rows:
        out[r.status.value.lower()] += 1
        out["total"] += 1
    return out


# --------------------------------------------------------------------------- #
# Results                                                                     #
# --------------------------------------------------------------------------- #

def _grade(total: float) -> str:
    """Map a 0-100 total to a letter grade."""
    if total >= 70:
        return "A"
    if total >= 60:
        return "B"
    if total >= 50:
        return "C"
    if total >= 45:
        return "D"
    if total >= 40:
        return "E"
    return "F"


def record_result(session: Session, *, student_id: int,
                  class_id: Optional[int] = None,
                  academic_session_id: Optional[int] = None,
                  subject: str, term_number: int,
                  ca_score: float = 0.0, exam_score: float = 0.0,
                  teacher_employee_id: Optional[int] = None,
                  remarks: Optional[str] = None) -> StudentResult:
    """Record one subject result for a student in a term. total = ca + exam,
    grade derived via _grade(total). Nothing posts to the GL."""
    authz.require_perm("manage.school")
    if session.get(Student, student_id) is None:
        raise ValueError("Student not found.")
    if not (subject or "").strip():
        raise ValueError("Subject is required.")
    if term_number not in (1, 2, 3):
        raise ValueError("term_number must be 1, 2 or 3.")
    ca = float(ca_score or 0.0)
    exam = float(exam_score or 0.0)
    total = round(ca + exam, 2)
    obj = StudentResult(student_id=student_id, class_id=class_id,
                        academic_session_id=academic_session_id,
                        subject=subject.strip(), term_number=term_number,
                        ca_score=ca, exam_score=exam, total=total,
                        grade=_grade(total),
                        teacher_employee_id=teacher_employee_id,
                        remarks=(remarks or None))
    session.add(obj); session.flush()
    return obj


def report_card(session: Session, student_id: int, academic_session_id: int,
                term_number: int) -> dict:
    """Read-only term report card: the student's per-subject results plus the
    average total for the (session, term)."""
    stu = session.get(Student, student_id)
    rows = session.execute(select(StudentResult).where(
        StudentResult.student_id == student_id,
        StudentResult.academic_session_id == academic_session_id,
        StudentResult.term_number == term_number)
        .order_by(StudentResult.subject)).scalars().all()
    results = [{"subject": r.subject, "ca_score": r.ca_score,
                "exam_score": r.exam_score, "total": r.total,
                "grade": r.grade, "remarks": r.remarks} for r in rows]
    average = round(sum(r.total for r in rows) / len(rows), 2) if rows else 0.0
    return {
        "student": (f"{stu.first_name} {stu.last_name}" if stu else None),
        "results": results,
        "average": average,
    }
