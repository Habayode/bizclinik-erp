"""School Phase 5 — teaching staff profiles and the read-only school dashboard.

A teacher profile is keyed on employee_id, so re-assigning updates the existing
row instead of duplicating it. The dashboard rolls up enrolment, staff and the
fee position from the data already captured by earlier phases and the sales/AR
engine — it never posts to the GL.
"""
from __future__ import annotations

from datetime import date

import pytest


def _an_employee(s, code="EMP-001", name="Mr. Tunde Bello"):
    from bizclinik_erp.models import Employee
    emp = Employee(code=code, name=name)
    s.add(emp); s.flush()
    return emp


def test_upsert_teacher_profile_creates_then_updates(fresh_db):
    """Two upserts for the same employee yield ONE profile (no duplicate); the
    second call updates the existing row's fields."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_staff
    from bizclinik_erp.models import StaffType, TeacherProfile
    from sqlalchemy import func, select
    with get_session() as s:
        emp = _an_employee(s)
        p1 = school_staff.upsert_teacher_profile(
            s, employee_id=emp.id, qualification="B.Sc Maths",
            subjects_taught="Maths")
        assert p1.staff_type == StaffType.TEACHING
        assert p1.qualification == "B.Sc Maths"
        # re-assign the same employee -> update, not a new row
        p2 = school_staff.upsert_teacher_profile(
            s, employee_id=emp.id, staff_type="NON_TEACHING",
            qualification="M.Ed", subjects_taught="Further Maths",
            classes_assigned="SS1A")
        assert p2.id == p1.id
        assert p2.staff_type == StaffType.NON_TEACHING
        assert p2.qualification == "M.Ed"
        assert p2.classes_assigned == "SS1A"
        n = s.execute(select(func.count()).select_from(
            TeacherProfile)).scalar_one()
        assert n == 1
        # list_teachers joins through to the employee
        teachers = school_staff.list_teachers(s)
        assert len(teachers) == 1
        assert teachers[0]["name"] == "Mr. Tunde Bello"
        assert teachers[0]["staff_type"] == "NON_TEACHING"


def test_upsert_teacher_profile_unknown_employee_rejected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_staff
    with get_session() as s:
        with pytest.raises(ValueError, match="Employee not found"):
            school_staff.upsert_teacher_profile(s, employee_id=99999)


def _setup_school(s):
    """Education COA + TUI fee (50,000, term 1) + class + TWO enrolled
    students. Returns (sess, cls, ft, s1, s2)."""
    from bizclinik_erp.services import school, school_enrol, coa_templates
    coa_templates.apply_template(s, "education")
    sess = school.create_academic_session(s, session_code="2025/2026",
                                           make_current=True)
    cls = school.create_school_class(s, class_code="JSS1A",
                                     name="Junior Secondary 1A", form_level=1)
    ft = school.create_fee_type(s, code="TUI", name="Tuition",
                                income_account_code="4400")
    school.set_fee_schedule(s, academic_session_id=sess.id, fee_type_id=ft.id,
                            class_id=cls.id, term_number=1, amount=50000)
    s1 = school_enrol.enrol_student(s, first_name="Ada", last_name="Obi",
                                    class_id=cls.id, academic_session_id=sess.id)
    s2 = school_enrol.enrol_student(s, first_name="Bode", last_name="Cole",
                                    class_id=cls.id, academic_session_id=sess.id)
    return sess, cls, ft, s1, s2


def test_school_dashboard_counts_and_fees(fresh_db):
    """After enrolling 2 students and billing them, the dashboard reports
    total_students == 2 and fees_billed matching the issued invoices."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_staff, school_billing
    with get_session() as s:
        sess, cls, ft, s1, s2 = _setup_school(s)
        # one teaching-staff profile
        emp = _an_employee(s)
        school_staff.upsert_teacher_profile(s, employee_id=emp.id)
        # bill both students for term 1 (50,000 each)
        res = school_billing.generate_class_fees(
            s, class_id=cls.id, academic_session_id=sess.id, term_number=1,
            invoice_date=date(2026, 1, 10))
        assert res["billed"] == 2

        kpi = school_staff.school_dashboard(s, academic_session_id=sess.id)
        assert kpi["total_students"] == 2
        assert kpi["total_teachers"] == 1
        assert kpi["fees_billed"] == 100000.0      # 2 x 50,000
        assert kpi["fees_collected"] == 0.0
        assert kpi["fees_outstanding"] == 100000.0
        assert kpi["defaulter_count"] == 2
        # enrolment_by_class reflects the two active students in JSS1A
        ebc = {r["class_code"]: r["count"] for r in kpi["enrolment_by_class"]}
        assert ebc.get("JSS1A") == 2


def test_dashboard_defaulter_counts_students_not_term_invoices(fresh_db):
    """A student billed (and unpaid) across multiple terms is ONE defaulter, not
    one per term. Regression for defaulter_count exceeding the student count."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_staff, school_billing, school
    with get_session() as s:
        sess, cls, ft, s1, s2 = _setup_school(s)
        # add term-2 and term-3 fee cells so multi-term billing has something
        for term in (2, 3):
            school.set_fee_schedule(s, academic_session_id=sess.id,
                                    fee_type_id=ft.id, class_id=cls.id,
                                    term_number=term, amount=50000)
        # bill ONLY s1 for all three terms, all unpaid
        for term in (1, 2, 3):
            school_billing.bill_student(s, student_id=s1.id,
                                        academic_session_id=sess.id,
                                        term_number=term,
                                        invoice_date=date(2026, 1, 10))
        kpi = school_staff.school_dashboard(s, academic_session_id=sess.id)
        # 3 outstanding term-invoices, but exactly ONE defaulting student
        assert kpi["defaulter_count"] == 1
        # and it matches the (distinct-student) defaulters list
        assert len(school_billing.defaulters(s, academic_session_id=sess.id)) == 1


def test_school_dashboard_collected_after_payment(fresh_db):
    """A full payment moves the money from outstanding to collected and clears
    the defaulter."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_staff, school_billing
    from bizclinik_erp.models import BankAccount
    from sqlalchemy import select
    with get_session() as s:
        sess, cls, ft, s1, s2 = _setup_school(s)
        b1 = school_billing.bill_student(
            s, student_id=s1.id, academic_session_id=sess.id, term_number=1,
            invoice_date=date(2026, 1, 10))
        bank = s.execute(select(BankAccount).order_by(
            BankAccount.id)).scalars().first()
        school_billing.record_fee_payment(
            s, student_id=s1.id, sales_invoice_id=b1.sales_invoice_id,
            amount=50000, payment_date=date(2026, 1, 15),
            bank_account_id=bank.id)
        kpi = school_staff.school_dashboard(s, academic_session_id=sess.id)
        assert kpi["fees_billed"] == 50000.0
        assert kpi["fees_collected"] == 50000.0
        assert kpi["fees_outstanding"] == 0.0
        assert kpi["defaulter_count"] == 0
