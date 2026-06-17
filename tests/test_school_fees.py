"""School Phase 2 — fee billing. The linchpin: billing a student raises a real
SalesInvoice through the normal sales engine, so the fee revenue lands in the
fee's education income account (4400), and re-running the bill is idempotent (no
double invoicing)."""
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


def test_bill_student_posts_invoice_to_income_account(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing
    from bizclinik_erp.services.ledger import account_balance
    from bizclinik_erp.models import Account, SalesInvoice, StudentFeeBilling
    from sqlalchemy import func, select
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        billing = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        assert billing is not None
        assert billing.total_amount == 50000.0
        # a real SalesInvoice was raised for the student's customer
        inv = s.get(SalesInvoice, billing.sales_invoice_id)
        assert inv is not None
        assert inv.customer_id == student.customer_id
        assert inv.grand_total == 50000.0      # VAT-exempt fee
        # revenue posted to 4400 Tuition (income = +credit balance), not 4100
        acct_id = s.execute(select(Account.id).where(
            Account.code == "4400")).scalar_one()
        assert account_balance(s, acct_id) == 50000.0
        # exactly one billing row + one invoice
        assert s.execute(select(func.count()).select_from(
            StudentFeeBilling)).scalar_one() == 1
        assert s.execute(select(func.count()).select_from(
            SalesInvoice)).scalar_one() == 1


def test_bill_student_is_idempotent(fresh_db):
    """Billing the same (student, session, term) twice must NOT double the GL
    balance nor raise a second invoice."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing
    from bizclinik_erp.services.ledger import account_balance
    from bizclinik_erp.models import Account, SalesInvoice, StudentFeeBilling
    from sqlalchemy import func, select
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        first = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        again = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=1, invoice_date=date(2026, 1, 10))
        # same billing row returned, no duplicate
        assert again.id == first.id
        assert s.execute(select(func.count()).select_from(
            StudentFeeBilling)).scalar_one() == 1
        assert s.execute(select(func.count()).select_from(
            SalesInvoice)).scalar_one() == 1
        acct_id = s.execute(select(Account.id).where(
            Account.code == "4400")).scalar_one()
        assert account_balance(s, acct_id) == 50000.0   # not 100,000


def test_bill_student_no_schedule_returns_none(fresh_db):
    """A student whose class has no fee-grid cells for the term yields nothing
    to bill (no invoice, no billing row)."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing
    from bizclinik_erp.models import SalesInvoice, StudentFeeBilling
    from sqlalchemy import func, select
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        # term 2 has no schedule rows
        out = school_billing.bill_student(
            s, student_id=student.id, academic_session_id=sess.id,
            term_number=2, invoice_date=date(2026, 1, 10))
        assert out is None
        assert s.execute(select(func.count()).select_from(
            StudentFeeBilling)).scalar_one() == 0
        assert s.execute(select(func.count()).select_from(
            SalesInvoice)).scalar_one() == 0


def test_generate_class_fees_bills_then_skips(fresh_db):
    """A class run bills active students once; a second run skips them all."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_billing, school_enrol
    from bizclinik_erp.services.ledger import account_balance
    from bizclinik_erp.models import Account
    from sqlalchemy import select
    with get_session() as s:
        sess, cls, ft, student = _setup(s)
        # a second student in the same class
        school_enrol.enrol_student(s, first_name="Bode", last_name="Cole",
                                   class_id=cls.id, academic_session_id=sess.id)
        res = school_billing.generate_class_fees(
            s, class_id=cls.id, academic_session_id=sess.id, term_number=1,
            invoice_date=date(2026, 1, 10))
        assert res["billed"] == 2
        assert res["skipped"] == 0
        assert res["errors"] == []
        acct_id = s.execute(select(Account.id).where(
            Account.code == "4400")).scalar_one()
        assert account_balance(s, acct_id) == 100000.0   # 2 × 50,000
        # re-run: everyone already billed
        res2 = school_billing.generate_class_fees(
            s, class_id=cls.id, academic_session_id=sess.id, term_number=1,
            invoice_date=date(2026, 1, 10))
        assert res2["billed"] == 0
        assert res2["skipped"] == 2
        assert account_balance(s, acct_id) == 100000.0
