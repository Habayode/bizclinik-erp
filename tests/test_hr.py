"""HR module: employees, recruitment (openings → candidates → applications →
hire) and leave management."""
from __future__ import annotations

from datetime import date

import pytest


def test_create_and_list_employees(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    with get_session() as s:
        e1 = hr.create_employee(s, name="Ada Obi", department="Sales",
                                job_title="Associate", monthly_gross=250000)
        e2 = hr.create_employee(s, name="Bola Eze", monthly_gross=300000)
        assert e1.code != e2.code            # auto codes are unique
        assert e1.annual_leave_days == 20.0  # default entitlement
    with get_session() as s:
        emps = hr.list_employees(s)
        assert len(emps) == 2
        assert hr.headcount(s) == {"total": 2, "active": 2, "inactive": 0}


def test_deactivate_employee(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    with get_session() as s:
        e = hr.create_employee(s, name="Temp Worker")
        hr.set_employee_active(s, e.id, False)
    with get_session() as s:
        assert hr.headcount(s)["active"] == 0
        assert len(hr.list_employees(s, active_only=True)) == 0


def test_recruitment_pipeline_and_hire(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    from bizclinik_erp.models import ApplicationStage, OpeningStatus
    with get_session() as s:
        op = hr.create_opening(s, title="Cashier", department="Retail", headcount=1)
        cand = hr.add_candidate(s, name="Chidi N", email="chidi@x.com",
                                source="board")
        app = hr.apply(s, opening_id=op.id, candidate_id=cand.id)
        assert app.stage == ApplicationStage.APPLIED
        hr.move_application(s, app.id, ApplicationStage.INTERVIEW)
        # Hire: creates an Employee, closes the application, fills the opening.
        res = hr.hire_candidate(s, app.id, monthly_gross=180000, paye_rate=0.07)
        assert res["already_hired"] is False
        emp_id = res["employee_id"]
    with get_session() as s:
        emp = hr.list_employees(s)[0]
        assert emp.id == emp_id and emp.name == "Chidi N"
        op = hr.list_openings(s)[0]
        assert op.status == OpeningStatus.FILLED
        summ = hr.recruitment_summary(s)
        assert summ["hired"] == 1 and summ["open_openings"] == 0


def test_hire_is_idempotent(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    with get_session() as s:
        op = hr.create_opening(s, title="Dev")
        cand = hr.add_candidate(s, name="Pat")
        app = hr.apply(s, opening_id=op.id, candidate_id=cand.id)
        r1 = hr.hire_candidate(s, app.id)
        r2 = hr.hire_candidate(s, app.id)
        assert r2["already_hired"] is True
        assert r2["employee_id"] == r1["employee_id"]
    with get_session() as s:
        assert hr.headcount(s)["total"] == 1   # not hired twice


def test_apply_validates_refs(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    with get_session() as s:
        with pytest.raises(ValueError):
            hr.apply(s, opening_id=999, candidate_id=999)


def test_leave_request_approve_and_balance(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    from bizclinik_erp.models import LeaveType, LeaveStatus
    with get_session() as s:
        emp = hr.create_employee(s, name="Ngozi", annual_leave_days=20)
        req = hr.request_leave(s, employee_id=emp.id, leave_type=LeaveType.ANNUAL,
                               start_date=date(2026, 6, 1), end_date=date(2026, 6, 5))
        assert req.days == 5.0                       # inclusive
        assert req.status == LeaveStatus.PENDING
        hr.decide_leave(s, req.id, approve=True)
        bal = hr.leave_balance(s, emp.id, year=2026)
        assert bal["entitlement"] == 20.0
        assert bal["taken"] == 5.0
        assert bal["remaining"] == 15.0


def test_pending_leave_does_not_reduce_balance(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    from bizclinik_erp.models import LeaveType
    with get_session() as s:
        emp = hr.create_employee(s, name="Sade", annual_leave_days=15)
        hr.request_leave(s, employee_id=emp.id, leave_type=LeaveType.ANNUAL,
                         start_date=date(2026, 3, 1), end_date=date(2026, 3, 3))
        # Pending (not approved) -> balance untouched.
        bal = hr.leave_balance(s, emp.id, year=2026)
        assert bal["taken"] == 0.0 and bal["remaining"] == 15.0
        assert hr.leave_summary(s)["pending"] == 1


def test_leave_rejects_bad_dates(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import hr
    from bizclinik_erp.models import LeaveType
    with get_session() as s:
        emp = hr.create_employee(s, name="Uche")
        with pytest.raises(ValueError):
            hr.request_leave(s, employee_id=emp.id, leave_type=LeaveType.SICK,
                             start_date=date(2026, 5, 10), end_date=date(2026, 5, 1))
