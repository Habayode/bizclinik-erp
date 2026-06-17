"""School Phase 3 — collections, statements, defaulters.

A fee payment routes through the normal sales/AR receipt engine (DR Bank / CR
AR), never a direct GL post from school code. student_balance rolls up the
student's SalesInvoices; partial payment leaves an outstanding balance and keeps
the student on the defaulters list, while full payment clears it to zero and
flips the invoice to PAID.
"""
from __future__ import annotations

from datetime import date

import pytest


def _setup(s):
    """Education COA + a TUI fee wired to 4400 + a class + a term-1 fee schedule
    (50,000) + one enrolled student. Returns (sess, cls, ft, student)."""
    from bizclinik_erp.services import school, school_enrol, coa_templates
    coa_templates.apply_template(s, "education")          # seeds 4400 Tuition etc.
    sess = school.create_academic_session(s, session_code="2025/2026",
                                           make_current=True)
    cls = school.create_school_class(s, class_code="JSS1A",
                                     name="Junior Secondary 1A", form_level=1)
    ft = school.create_fee_type(s, code="TUI", name="Tuition",
                                income_account_code="4400")
    school.set_fee_schedule(s, academic_session_id=sess.id, fee_type_id=ft.id,
                            class_id=cls.id, term_number=1, amount=50000)
    student = school_enrol.enrol_student(s, first_name="Ada", last_name="Obi",
                                         class_id=cls.id,
                                         academic_session_id=sess.id)
    return sess, cls, ft, student


def _a_bank_account(s):
    """First bank account seeded for the tenant (for the receipt)."""
    from bizclinik_erp.models import BankAccount
    from sqlalchemy import select
    return s.execute(select(BankAccount).order_by(BankAccount.id)).scalars().first()


def test_partial_payment_leaves_outstanding(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        billing = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        assert billing.total_amount == 50000.0
        bank = _a_bank_account(s)
        school_billing.record_fee_payment(
            s, student_id=student.id, sales_invoice_id=billing.sales_invoice_id,
            amount=30000, payment_date=date(2026, 1, 15),
            bank_account_id=bank.id, reference="PT-001")
        bal = school_billing.student_balance(s, student.id)
        assert bal["billed"] == 50000.0
        assert bal["paid"] == 30000.0
        assert bal["outstanding"] == 20000.0


def test_full_payment_clears_and_marks_paid(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing
    from bizclinik_erp.models import DocStatus, SalesInvoice
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        billing = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        bank = _a_bank_account(s)
        school_billing.record_fee_payment(
            s, student_id=student.id, sales_invoice_id=billing.sales_invoice_id,
            amount=50000, payment_date=date(2026, 1, 20),
            bank_account_id=bank.id, reference="PT-FULL")
        bal = school_billing.student_balance(s, student.id)
        assert bal["outstanding"] == 0.0
        inv = s.get(SalesInvoice, billing.sales_invoice_id)
        assert inv.status == DocStatus.PAID


def test_defaulters_lists_then_drops_after_payment(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        billing = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        # while outstanding > 0 the student is a defaulter
        defs = school_billing.defaulters(s, academic_session_id=sess.id)
        assert len(defs) == 1
        assert defs[0]["admission_no"] == student.admission_no
        assert defs[0]["outstanding"] == 50000.0
        # class roll shows the student too
        roll = school_billing.class_fee_status(
            s, class_id=cls.id, academic_session_id=sess.id)
        assert len(roll) == 1
        assert roll[0]["outstanding"] == 50000.0
        # pay in full -> drops off the defaulters list
        bank = _a_bank_account(s)
        school_billing.record_fee_payment(
            s, student_id=student.id, sales_invoice_id=billing.sales_invoice_id,
            amount=50000, payment_date=date(2026, 1, 20),
            bank_account_id=bank.id)
        assert school_billing.defaulters(s, academic_session_id=sess.id) == []


def test_defaulters_sorted_by_outstanding_desc(fresh_db):
    """Two billed students with different balances sort highest-first."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing, school_enrol
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        s2 = school_enrol.enrol_student(s, first_name="Bode", last_name="Cole",
                                        class_id=cls.id,
                                        academic_session_id=sess.id)
        b1 = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        school_billing.bill_student(
            s, student_id=s2.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        bank = _a_bank_account(s)
        # student 1 pays 40,000 -> 10,000 left; student 2 still owes 50,000
        school_billing.record_fee_payment(
            s, student_id=student.id, sales_invoice_id=b1.sales_invoice_id,
            amount=40000, payment_date=date(2026, 1, 15),
            bank_account_id=bank.id)
        defs = school_billing.defaulters(s, academic_session_id=sess.id)
        assert [d["outstanding"] for d in defs] == [50000.0, 10000.0]
