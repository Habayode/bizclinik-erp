"""Payroll: build payslips from employee master data, post a single payroll JE.

PAYE is **graduated** (CITA Sixth Schedule bands with CRA + pension relief —
see services.paye). An employee with an explicit `paye_rate > 0` keeps that
flat effective rate as an override; otherwise the graduated calculation
applies. Pension: employee 8% + employer 10% of gross are the statutory
minimums.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    BankAccount,
    DocStatus,
    Employee,
    PayrollPayslip,
    PayrollRun,
)
from .ledger import JELine, post_journal
from .numbering import next_number
from .paye import compute_paye_monthly
from .. import authz


@dataclass
class PayslipInput:
    employee_id: int
    gross: Optional[float] = None       # default: employee.monthly_gross
    other_deductions: float = 0.0


def _accts(session: Session) -> dict[str, Account]:
    codes = {
        "SAL": "6100", "PEN_EXP": "6110",
        "PAYE_LIA": "2130", "PEN_LIA": "2140",
    }
    out: dict[str, Account] = {}
    for k, c in codes.items():
        a = session.execute(select(Account).where(Account.code == c)).scalar_one_or_none()
        if not a:
            raise RuntimeError(f"Account {c} ({k}) missing — seed defaults.")
        out[k] = a
    return out


def run_payroll(
    session: Session, *,
    period_start: date, period_end: date, pay_date: date,
    inputs: Iterable[PayslipInput],
    bank_account_id: int,
    notes: Optional[str] = None,
) -> PayrollRun:
    authz.require_perm("run.payroll")
    accts = _accts(session)
    bank = session.get(BankAccount, bank_account_id)
    if not bank:
        raise ValueError("Bank account required.")

    run = PayrollRun(
        number=next_number(session, "PR", pay_date),
        period_start=period_start, period_end=period_end, pay_date=pay_date,
        notes=notes, status=DocStatus.DRAFT,
    )
    session.add(run)
    session.flush()

    total_gross = total_paye = total_pen_emp = total_pen_er = 0.0
    total_other = total_net = 0.0

    for inp in inputs:
        emp = session.get(Employee, inp.employee_id)
        if not emp:
            raise ValueError(f"Employee {inp.employee_id} not found.")
        gross = inp.gross if inp.gross is not None else emp.monthly_gross
        if (emp.paye_rate or 0) > 0:
            # Explicit flat effective rate kept as a per-employee override.
            paye = round(gross * emp.paye_rate, 2)
        else:
            # Graduated CITA bands with CRA + pension relief (services.paye).
            paye = compute_paye_monthly(
                gross, pension_employee_rate=emp.pension_rate or 0.0
            ).paye_monthly
        pen_emp = round(gross * (emp.pension_rate or 0), 2)
        pen_er = round(gross * (emp.pension_employer_rate or 0), 2)
        other = round(inp.other_deductions, 2)
        net = round(gross - paye - pen_emp - other, 2)

        slip = PayrollPayslip(
            run_id=run.id, employee_id=emp.id,
            gross=gross, paye=paye,
            pension_employee=pen_emp, pension_employer=pen_er,
            other_deductions=other, net_pay=net,
        )
        run.payslips.append(slip)
        total_gross += gross; total_paye += paye
        total_pen_emp += pen_emp; total_pen_er += pen_er
        total_other += other; total_net += net

    if total_gross == 0:
        run.status = DocStatus.POSTED
        session.flush()
        return run

    je_lines = [
        JELine(account_id=accts["SAL"].id, debit=round(total_gross, 2),
               memo=f"Payroll {run.number} — gross"),
    ]
    if total_pen_er:
        je_lines.append(JELine(account_id=accts["PEN_EXP"].id, debit=total_pen_er,
                                memo=f"Payroll {run.number} — employer pension"))
    if total_paye:
        je_lines.append(JELine(account_id=accts["PAYE_LIA"].id, credit=total_paye,
                                memo="PAYE withheld"))
    pension_liability = round(total_pen_emp + total_pen_er, 2)
    if pension_liability:
        je_lines.append(JELine(account_id=accts["PEN_LIA"].id, credit=pension_liability,
                                memo="Pension payable"))
    if total_other:
        je_lines.append(JELine(account_id=accts["SAL"].id, credit=total_other,
                                memo="Other deductions netted"))
    # Net pay paid out of the bank
    je_lines.append(JELine(account_id=bank.gl_account_id, credit=round(total_net, 2),
                            memo=f"Net pay disbursement — {run.number}"))

    je = post_journal(
        session, pay_date,
        f"Payroll run {run.number} ({period_start}–{period_end})",
        je_lines, source_kind="PAYROLL", source_id=run.id,
    )
    run.je_id = je.id
    run.status = DocStatus.POSTED
    session.flush()
    return run
