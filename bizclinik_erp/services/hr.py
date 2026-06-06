"""HR service — employees, recruitment (openings → candidates → applications)
and leave management.

Recruitment flow mirrors CRM: open a JobOpening, add Candidates, file
JobApplications, move them through stages, and `hire` a candidate (which
creates a real Employee so Payroll takes over). Leave: request → approve/reject,
with a simple annual-entitlement balance per employee.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    ApplicationStage, Candidate, Employee, JobApplication, JobOpening,
    LeaveRequest, LeaveStatus, LeaveType, OpeningStatus,
)
from ..models.hr import CLOSED_APP_STAGES, OPEN_APP_STAGES


def _now() -> datetime:
    return datetime.utcnow()


# --------------------------------------------------------------------------- #
# Employees                                                                   #
# --------------------------------------------------------------------------- #

def _unique_employee_code(session: Session, name: str) -> str:
    base = "EMP"
    n = session.execute(select(func.count(Employee.id))).scalar() or 0
    code = f"{base}{n + 1:04d}"
    while session.execute(select(Employee).where(Employee.code == code)).scalar_one_or_none():
        n += 1
        code = f"{base}{n + 1:04d}"
    return code


def create_employee(session: Session, *, name: str, email: Optional[str] = None,
                    phone: Optional[str] = None, department: Optional[str] = None,
                    job_title: Optional[str] = None,
                    employment_type: Optional[str] = None,
                    monthly_gross: float = 0.0, paye_rate: float = 0.0,
                    pension_rate: float = 0.08, pension_employer_rate: float = 0.10,
                    annual_leave_days: float = 20.0,
                    hire_date: Optional[date] = None,
                    code: Optional[str] = None) -> Employee:
    if not (name or "").strip():
        raise ValueError("Employee name required.")
    emp = Employee(
        code=code or _unique_employee_code(session, name),
        name=name.strip(), email=email, phone=phone,
        department=department, job_title=job_title,
        employment_type=employment_type, monthly_gross=monthly_gross,
        paye_rate=paye_rate, pension_rate=pension_rate,
        pension_employer_rate=pension_employer_rate,
        annual_leave_days=annual_leave_days,
        hire_date=(datetime(hire_date.year, hire_date.month, hire_date.day)
                   if hire_date else _now()),
        is_active=True,
    )
    session.add(emp)
    session.flush()
    return emp


def list_employees(session: Session, *, active_only: bool = False) -> list[Employee]:
    stmt = select(Employee).order_by(Employee.code)
    if active_only:
        stmt = stmt.where(Employee.is_active == True)  # noqa: E712
    return list(session.execute(stmt).scalars())


def set_employee_active(session: Session, employee_id: int, active: bool) -> Employee:
    emp = session.get(Employee, employee_id)
    if not emp:
        raise ValueError(f"Employee {employee_id} not found.")
    emp.is_active = active
    session.flush()
    return emp


def headcount(session: Session) -> dict:
    total = session.execute(select(func.count(Employee.id))).scalar() or 0
    active = session.execute(
        select(func.count(Employee.id)).where(Employee.is_active == True)  # noqa: E712
    ).scalar() or 0
    return {"total": int(total), "active": int(active), "inactive": int(total - active)}


# --------------------------------------------------------------------------- #
# Recruitment                                                                 #
# --------------------------------------------------------------------------- #

def create_opening(session: Session, *, title: str, department: Optional[str] = None,
                   location: Optional[str] = None, employment_type: Optional[str] = None,
                   headcount: int = 1, description: Optional[str] = None,
                   owner_user_id: Optional[int] = None) -> JobOpening:
    if not (title or "").strip():
        raise ValueError("Job title required.")
    op = JobOpening(
        title=title.strip(), department=department, location=location,
        employment_type=employment_type, headcount=max(1, int(headcount or 1)),
        description=description, owner_user_id=owner_user_id,
        status=OpeningStatus.OPEN,
    )
    session.add(op)
    session.flush()
    return op


def list_openings(session: Session, *, open_only: bool = False) -> list[JobOpening]:
    stmt = select(JobOpening).order_by(JobOpening.created_at.desc())
    if open_only:
        stmt = stmt.where(JobOpening.status == OpeningStatus.OPEN)
    return list(session.execute(stmt).scalars())


def set_opening_status(session: Session, opening_id: int,
                       status: OpeningStatus) -> JobOpening:
    op = session.get(JobOpening, opening_id)
    if not op:
        raise ValueError(f"Opening {opening_id} not found.")
    op.status = status
    op.updated_at = _now()
    session.flush()
    return op


def add_candidate(session: Session, *, name: str, email: Optional[str] = None,
                  phone: Optional[str] = None, source: Optional[str] = None,
                  resume_url: Optional[str] = None,
                  notes: Optional[str] = None) -> Candidate:
    if not (name or "").strip():
        raise ValueError("Candidate name required.")
    c = Candidate(name=name.strip(), email=email, phone=phone, source=source,
                  resume_url=resume_url, notes=notes)
    session.add(c)
    session.flush()
    return c


def list_candidates(session: Session) -> list[Candidate]:
    return list(session.execute(
        select(Candidate).order_by(Candidate.created_at.desc())).scalars())


def apply(session: Session, *, opening_id: int, candidate_id: int,
          applied_date: Optional[date] = None,
          notes: Optional[str] = None) -> JobApplication:
    if not session.get(JobOpening, opening_id):
        raise ValueError(f"Opening {opening_id} not found.")
    if not session.get(Candidate, candidate_id):
        raise ValueError(f"Candidate {candidate_id} not found.")
    app = JobApplication(
        opening_id=opening_id, candidate_id=candidate_id,
        applied_date=applied_date or date.today(),
        stage=ApplicationStage.APPLIED, notes=notes,
    )
    session.add(app)
    session.flush()
    return app


def move_application(session: Session, application_id: int,
                     stage: ApplicationStage) -> JobApplication:
    app = session.get(JobApplication, application_id)
    if not app:
        raise ValueError(f"Application {application_id} not found.")
    app.stage = stage
    app.updated_at = _now()
    if stage in CLOSED_APP_STAGES:
        app.closed_at = _now()
    else:
        app.closed_at = None
    session.flush()
    return app


def list_applications(session: Session, *, opening_id: Optional[int] = None,
                      open_only: bool = False) -> list[JobApplication]:
    stmt = select(JobApplication).order_by(JobApplication.created_at.desc())
    if opening_id is not None:
        stmt = stmt.where(JobApplication.opening_id == opening_id)
    if open_only:
        stmt = stmt.where(JobApplication.stage.in_(OPEN_APP_STAGES))
    return list(session.execute(stmt).scalars())


def hire_candidate(session: Session, application_id: int, *,
                   monthly_gross: float = 0.0, paye_rate: float = 0.0,
                   department: Optional[str] = None, job_title: Optional[str] = None,
                   employment_type: Optional[str] = None,
                   fill_opening: bool = True) -> dict:
    """Hire the candidate on an application: create an Employee, mark the
    application HIRED, and optionally mark the opening FILLED. Returns ids."""
    app = session.get(JobApplication, application_id)
    if not app:
        raise ValueError(f"Application {application_id} not found.")
    if app.employee_id:
        return {"application_id": app.id, "employee_id": app.employee_id,
                "already_hired": True}
    cand = session.get(Candidate, app.candidate_id)
    opening = session.get(JobOpening, app.opening_id)
    emp = create_employee(
        session, name=cand.name, email=cand.email, phone=cand.phone,
        department=department or (opening.department if opening else None),
        job_title=job_title or (opening.title if opening else None),
        employment_type=employment_type or (opening.employment_type if opening else None),
        monthly_gross=monthly_gross, paye_rate=paye_rate,
    )
    app.employee_id = emp.id
    app.stage = ApplicationStage.HIRED
    app.closed_at = _now()
    app.updated_at = _now()
    if fill_opening and opening:
        opening.status = OpeningStatus.FILLED
        opening.updated_at = _now()
    session.flush()
    return {"application_id": app.id, "employee_id": emp.id,
            "opening_id": app.opening_id, "already_hired": False}


def recruitment_summary(session: Session) -> dict:
    open_count = session.execute(
        select(func.count(JobOpening.id)).where(
            JobOpening.status == OpeningStatus.OPEN)).scalar() or 0
    cand_count = session.execute(select(func.count(Candidate.id))).scalar() or 0
    by_stage = {}
    for st in ApplicationStage:
        n = session.execute(
            select(func.count(JobApplication.id)).where(
                JobApplication.stage == st)).scalar() or 0
        by_stage[st.value] = int(n)
    in_pipeline = sum(by_stage[s.value] for s in OPEN_APP_STAGES)
    hired = by_stage[ApplicationStage.HIRED.value]
    return {"open_openings": int(open_count), "candidates": int(cand_count),
            "in_pipeline": int(in_pipeline), "hired": int(hired),
            "by_stage": by_stage}


# --------------------------------------------------------------------------- #
# Leave management                                                            #
# --------------------------------------------------------------------------- #

def _inclusive_days(start: date, end: date) -> int:
    return (end - start).days + 1


def request_leave(session: Session, *, employee_id: int, leave_type: LeaveType,
                  start_date: date, end_date: date,
                  days: Optional[float] = None,
                  reason: Optional[str] = None) -> LeaveRequest:
    emp = session.get(Employee, employee_id)
    if not emp:
        raise ValueError(f"Employee {employee_id} not found.")
    if end_date < start_date:
        raise ValueError("End date cannot be before start date.")
    d = days if days is not None else float(_inclusive_days(start_date, end_date))
    req = LeaveRequest(
        employee_id=employee_id, leave_type=leave_type,
        start_date=start_date, end_date=end_date, days=d,
        status=LeaveStatus.PENDING, reason=reason,
    )
    session.add(req)
    session.flush()
    return req


def decide_leave(session: Session, request_id: int, *, approve: bool,
                 approver_user_id: Optional[int] = None) -> LeaveRequest:
    req = session.get(LeaveRequest, request_id)
    if not req:
        raise ValueError(f"Leave request {request_id} not found.")
    req.status = LeaveStatus.APPROVED if approve else LeaveStatus.REJECTED
    req.approver_user_id = approver_user_id
    req.decided_at = _now()
    session.flush()
    return req


def cancel_leave(session: Session, request_id: int) -> LeaveRequest:
    req = session.get(LeaveRequest, request_id)
    if not req:
        raise ValueError(f"Leave request {request_id} not found.")
    req.status = LeaveStatus.CANCELLED
    session.flush()
    return req


def list_leave(session: Session, *, employee_id: Optional[int] = None,
               status: Optional[LeaveStatus] = None) -> list[LeaveRequest]:
    stmt = select(LeaveRequest).order_by(LeaveRequest.start_date.desc())
    if employee_id is not None:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(LeaveRequest.status == status)
    return list(session.execute(stmt).scalars())


def leave_balance(session: Session, employee_id: int, *,
                  year: Optional[int] = None) -> dict:
    """Annual-leave balance: entitlement minus APPROVED annual days this year."""
    emp = session.get(Employee, employee_id)
    if not emp:
        raise ValueError(f"Employee {employee_id} not found.")
    yr = year or date.today().year
    taken = session.execute(
        select(func.coalesce(func.sum(LeaveRequest.days), 0.0)).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.leave_type == LeaveType.ANNUAL,
            LeaveRequest.status == LeaveStatus.APPROVED,
            func.extract("year", LeaveRequest.start_date) == yr,
        )).scalar() or 0.0
    entitlement = float(emp.annual_leave_days or 0.0)
    return {"employee_id": employee_id, "year": yr,
            "entitlement": entitlement, "taken": float(taken),
            "remaining": round(entitlement - float(taken), 2)}


def leave_summary(session: Session) -> dict:
    pending = session.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.status == LeaveStatus.PENDING)).scalar() or 0
    approved = session.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.status == LeaveStatus.APPROVED)).scalar() or 0
    return {"pending": int(pending), "approved": int(approved)}
