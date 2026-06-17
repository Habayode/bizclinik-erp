"""School module — Phase 0 scaffolding (academic calendar, classes, fee grid)
and the linchpin: a fee billed through the normal sales cycle posts its revenue
to the fee's education income account (no parallel ledger)."""
from __future__ import annotations

from datetime import date

import pytest


def test_create_session_term_class(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school
    with get_session() as s:
        sess = school.create_academic_session(
            s, session_code="2025/2026", make_current=True)
        t1 = school.create_term(s, academic_session_id=sess.id, term_number=1)
        cls = school.create_school_class(s, class_code="JSS1A",
                                         name="Junior Secondary 1A", form_level=1)
        assert sess.is_current and t1.term_number == 1 and cls.class_code == "JSS1A"
        # duplicates rejected
        with pytest.raises(ValueError, match="already exists"):
            school.create_academic_session(s, session_code="2025/2026")
        with pytest.raises(ValueError, match="already exists"):
            school.create_term(s, academic_session_id=sess.id, term_number=1)


def test_fee_type_wires_product_to_income_account(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school, coa_templates
    from bizclinik_erp.models import FeeType, Product, Account
    from sqlalchemy import select
    with get_session() as s:
        coa_templates.apply_template(s, "education")   # seeds 4400 Tuition etc.
        ft = school.create_fee_type(s, code="TUI", name="Tuition",
                                    income_account_code="4400")
        prod = s.get(Product, ft.product_id)
        acct = s.get(Account, prod.income_account_id)
        assert prod.is_stockable is False
        assert acct.code == "4400"
        # bad account rejected
        with pytest.raises(ValueError, match="not found or not postable"):
            school.create_fee_type(s, code="BAD", name="Bad", income_account_code="9999")


def test_fee_billed_via_sales_posts_to_income_account(fresh_db):
    """The whole design rests on this: invoicing a fee product credits the fee's
    income account (4400), not the generic 4100 Sales."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school, coa_templates, sales
    from bizclinik_erp.services.ledger import account_balance
    from bizclinik_erp.models import Customer, FeeType
    from sqlalchemy import select
    with get_session() as s:
        coa_templates.apply_template(s, "education")
        ft = school.create_fee_type(s, code="TUI", name="Tuition",
                                    income_account_code="4400")
        prod_id = ft.product_id
        s.add(Customer(code="STU-0001", name="Ada (parent)"))
        s.flush()
        cust_id = s.execute(select(Customer.id).where(
            Customer.code == "STU-0001")).scalar_one()
    with get_session() as s:
        inv = sales.issue_invoice(
            s, customer_id=cust_id, invoice_date=date(2026, 1, 10),
            lines=[sales.LineInput(product_id=prod_id, description="Tuition — Term 1",
                                   qty=1, unit_price=50000, tax_rate=0.0)])
        assert inv.grand_total == 50000   # VAT-exempt fee
    with get_session() as s:
        from bizclinik_erp.models import Account
        # 4400 Tuition income should carry the 50,000 credit (income = +credit balance)
        acct_id = s.execute(select(Account.id).where(Account.code == "4400")).scalar_one()
        assert account_balance(s, acct_id) == 50000.0


def test_set_fee_schedule_idempotent(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school, coa_templates
    from bizclinik_erp.models import StudentFeeSchedule
    from sqlalchemy import select, func
    with get_session() as s:
        coa_templates.apply_template(s, "education")
        sess = school.create_academic_session(s, session_code="2025/2026")
        cls = school.create_school_class(s, class_code="JSS1A", name="JSS1A")
        ft = school.create_fee_type(s, code="TUI", name="Tuition",
                                    income_account_code="4400")
        school.set_fee_schedule(s, academic_session_id=sess.id, fee_type_id=ft.id,
                                class_id=cls.id, term_number=1, amount=50000)
        # re-set the same cell -> update, not duplicate
        school.set_fee_schedule(s, academic_session_id=sess.id, fee_type_id=ft.id,
                                class_id=cls.id, term_number=1, amount=55000)
        n = s.execute(select(func.count()).select_from(StudentFeeSchedule)).scalar_one()
        row = s.execute(select(StudentFeeSchedule)).scalars().one()
        assert n == 1 and row.amount == 55000
