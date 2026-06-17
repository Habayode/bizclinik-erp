"""School service — Phase 5: teaching staff profiles and the school dashboard.

A TeacherProfile is a school overlay on an existing Employee (qualification,
registration, subjects, class assignments). ``upsert_teacher_profile`` is keyed
on employee_id, so re-assigning a profile updates the existing row rather than
creating a duplicate. The dashboard is strictly read-only: it rolls up enrolment,
staff and the fee position (billed/collected/outstanding) from data already
captured by Phases 1-4 and the sales/AR engine — nothing here posts to the GL.
Mutating calls require the ``manage.school`` permission.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (Employee, SalesInvoice, SchoolClass, StaffType, Student,
                      StudentFeeBilling, StudentStatus, TeacherProfile)


# --------------------------------------------------------------------------- #
# Teaching staff profiles                                                     #
# --------------------------------------------------------------------------- #

def upsert_teacher_profile(session: Session, *, employee_id: int,
                           staff_type: str = "TEACHING",
                           qualification: Optional[str] = None,
                           registration_number: Optional[str] = None,
                           subjects_taught: Optional[str] = None,
                           classes_assigned: Optional[str] = None
                           ) -> TeacherProfile:
    """Create or update a teaching-staff profile for an Employee. Keyed on
    employee_id (one profile per employee) — a repeat call updates the existing
    row instead of inserting a duplicate."""
    authz.require_perm("manage.school")
    if session.get(Employee, employee_id) is None:
        raise ValueError("Employee not found.")
    st_type = StaffType(staff_type) if not isinstance(staff_type, StaffType) \
        else staff_type
    row = session.execute(select(TeacherProfile).where(
        TeacherProfile.employee_id == employee_id)).scalar_one_or_none()
    if row is None:
        row = TeacherProfile(employee_id=employee_id, staff_type=st_type,
                             qualification=(qualification or None),
                             registration_number=(registration_number or None),
                             subjects_taught=(subjects_taught or None),
                             classes_assigned=(classes_assigned or None))
        session.add(row)
    else:
        row.staff_type = st_type
        row.qualification = (qualification or None)
        row.registration_number = (registration_number or None)
        row.subjects_taught = (subjects_taught or None)
        row.classes_assigned = (classes_assigned or None)
    session.flush()
    return row


def list_teachers(session: Session) -> list[dict]:
    """All teaching-staff profiles joined to their Employee, ordered by name.
    Returns a list of {employee_code, name, staff_type, qualification,
    registration_number, subjects_taught, classes_assigned}."""
    rows = session.execute(
        select(TeacherProfile, Employee)
        .join(Employee, Employee.id == TeacherProfile.employee_id)
        .order_by(Employee.name)).all()
    out = []
    for prof, emp in rows:
        out.append({
            "employee_code": emp.code,
            "name": emp.name,
            "staff_type": prof.staff_type.value,
            "qualification": prof.qualification or "",
            "registration_number": prof.registration_number or "",
            "subjects_taught": prof.subjects_taught or "",
            "classes_assigned": prof.classes_assigned or "",
        })
    return out


# --------------------------------------------------------------------------- #
# School dashboard (read-only)                                                #
# --------------------------------------------------------------------------- #

def school_dashboard(session: Session,
                     academic_session_id: Optional[int] = None) -> dict:
    """Read-only KPI roll-up for the school. Reuses Phase 1-4 data and the
    sales/AR engine — does NOT post anything.

    Returns a dict with:
      - enrolment_by_class: list of {class_code, count} of ACTIVE students
      - total_students: count of ACTIVE students
      - total_teachers: count of TeacherProfile rows
      - fees_billed: sum of StudentFeeBilling.total_amount (scoped to the
        session when academic_session_id is given)
      - fees_collected: sum of amount_paid on those billings' invoices
      - fees_outstanding: fees_billed - fees_collected
      - defaulter_count: number of distinct students who still owe (a student
        billed across several terms counts once, not per term)
    """
    # Enrolment by class (active students only).
    enrol_rows = session.execute(
        select(SchoolClass.class_code, func.count(Student.id))
        .join(Student, Student.current_class_id == SchoolClass.id)
        .where(Student.status == StudentStatus.ACTIVE)
        .group_by(SchoolClass.id, SchoolClass.class_code)
        .order_by(SchoolClass.class_code)).all()
    enrolment_by_class = [{"class_code": code, "count": int(cnt)}
                          for code, cnt in enrol_rows]

    total_students = session.execute(
        select(func.count(Student.id)).where(
            Student.status == StudentStatus.ACTIVE)).scalar_one()

    total_teachers = session.execute(
        select(func.count(TeacherProfile.id))).scalar_one()

    # Fee position from the billing log (optionally scoped to the session).
    bq = select(StudentFeeBilling)
    if academic_session_id is not None:
        bq = bq.where(
            StudentFeeBilling.academic_session_id == academic_session_id)
    billings = session.execute(bq).scalars().all()

    fees_billed = round(sum(b.total_amount for b in billings), 2)
    fees_collected = 0.0
    outstanding_by_student: dict[int, float] = {}
    for b in billings:
        inv = b.sales_invoice
        if inv is None:
            continue
        fees_collected += inv.amount_paid
        outstanding_by_student[b.student_id] = round(
            outstanding_by_student.get(b.student_id, 0.0) + (inv.outstanding or 0.0), 2)
    fees_collected = round(fees_collected, 2)
    # A defaulter is a STUDENT who still owes — count once even if they owe
    # across several terms (not one per outstanding term-invoice).
    defaulter_count = sum(1 for bal in outstanding_by_student.values() if bal > 0.005)

    return {
        "enrolment_by_class": enrolment_by_class,
        "total_students": int(total_students),
        "total_teachers": int(total_teachers),
        "fees_billed": fees_billed,
        "fees_collected": fees_collected,
        "fees_outstanding": round(fees_billed - fees_collected, 2),
        "defaulter_count": defaulter_count,
    }
