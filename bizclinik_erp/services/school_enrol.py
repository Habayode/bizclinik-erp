"""School service — Phase 1: students and enrolment.

Enrolling a student creates a Customer (billing identity) FIRST, then the
Student record pointing at it, then an append-only StudentEnrolment row. Nothing
here posts to the GL — fees are billed later through the existing sales engine
against the student's Customer. Mutating calls require ``manage.school``.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (AcademicSession, Customer, SchoolClass, Student,
                      StudentEnrolment, StudentStatus)


def _next_admission_no(session: Session) -> str:
    """Sequential STU-0001 admission number from the current Student count."""
    n = session.execute(select(func.count()).select_from(Student)).scalar_one()
    return f"STU-{n + 1:04d}"


def enrol_student(session: Session, *, first_name: str, last_name: str,
                  class_id: int, academic_session_id: int,
                  admission_no: Optional[str] = None,
                  guardian_name: Optional[str] = None,
                  guardian_phone: Optional[str] = None,
                  guardian_email: Optional[str] = None,
                  dob: Optional[date] = None,
                  gender: Optional[str] = None,
                  date_admitted: Optional[date] = None) -> Student:
    """Create the Customer (billing identity) FIRST, then the Student, then a
    StudentEnrolment row. Auto-generates the admission number when omitted."""
    authz.require_perm("manage.school")
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not first or not last:
        raise ValueError("first_name and last_name are required.")
    if session.get(SchoolClass, class_id) is None:
        raise ValueError("Class not found.")
    if session.get(AcademicSession, academic_session_id) is None:
        raise ValueError("Academic session not found.")

    adm = (admission_no or "").strip() or _next_admission_no(session)
    if session.execute(select(Student).where(
            Student.admission_no == adm)).scalar_one_or_none():
        raise ValueError(f"Admission number {adm!r} already exists.")
    if session.execute(select(Customer).where(
            Customer.code == adm)).scalar_one_or_none():
        raise ValueError(f"A customer with code {adm!r} already exists.")

    full_name = f"{first} {last}"
    cust = Customer(code=adm, name=full_name, email=guardian_email,
                    phone=guardian_phone)
    session.add(cust); session.flush()

    student = Student(admission_no=adm, first_name=first, last_name=last,
                      dob=dob, gender=(gender or None), customer_id=cust.id,
                      current_class_id=class_id, status=StudentStatus.ACTIVE,
                      guardian_name=(guardian_name or None),
                      guardian_phone=(guardian_phone or None),
                      guardian_email=(guardian_email or None),
                      date_admitted=(date_admitted or date.today()))
    session.add(student); session.flush()

    enrol = StudentEnrolment(student_id=student.id,
                             academic_session_id=academic_session_id,
                             class_id=class_id, enrolment_status="ACTIVE")
    session.add(enrol); session.flush()
    return student


def list_students(session: Session, class_id: Optional[int] = None,
                  status: Optional[str] = None) -> list[Student]:
    q = select(Student).order_by(Student.admission_no)
    if class_id is not None:
        q = q.where(Student.current_class_id == class_id)
    if status is not None:
        q = q.where(Student.status == StudentStatus(status))
    return list(session.execute(q).scalars().all())


def withdraw_student(session: Session, student_id: int,
                     status: str = "WITHDRAWN") -> Student:
    """Mark a student off the roll and stamp their open enrolment row."""
    authz.require_perm("manage.school")
    student = session.get(Student, student_id)
    if student is None:
        raise ValueError("Student not found.")
    student.status = StudentStatus(status)
    student.status_date = date.today()
    student.is_active = False
    open_enrol = session.execute(
        select(StudentEnrolment).where(
            StudentEnrolment.student_id == student_id,
            StudentEnrolment.withdrawn_at.is_(None))
        .order_by(StudentEnrolment.enrolled_at.desc())).scalars().first()
    if open_enrol is not None:
        open_enrol.withdrawn_at = datetime.utcnow()
        open_enrol.enrolment_status = student.status.value
    session.flush()
    return student


def promote_student(session: Session, student_id: int, new_class_id: int,
                    academic_session_id: int) -> StudentEnrolment:
    """Move a student into a new class for a (new) session: update the
    denormalised current_class_id and append a fresh enrolment row."""
    authz.require_perm("manage.school")
    student = session.get(Student, student_id)
    if student is None:
        raise ValueError("Student not found.")
    if session.get(SchoolClass, new_class_id) is None:
        raise ValueError("Class not found.")
    if session.get(AcademicSession, academic_session_id) is None:
        raise ValueError("Academic session not found.")
    if session.execute(select(StudentEnrolment).where(
            StudentEnrolment.student_id == student_id,
            StudentEnrolment.academic_session_id == academic_session_id)
            ).scalar_one_or_none():
        raise ValueError("Student already has an enrolment for that session.")

    student.current_class_id = new_class_id
    enrol = StudentEnrolment(student_id=student_id,
                             academic_session_id=academic_session_id,
                             class_id=new_class_id, enrolment_status="ACTIVE")
    session.add(enrol); session.flush()
    return enrol
