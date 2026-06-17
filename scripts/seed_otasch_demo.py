"""Realistic demo data for the OTASCH school tenant — so you can click through
the whole school flow on otasch-erp.hagai.online before the school's real data
lands. Run against the ACTIVE tenant (set otasch active first).

    python scripts/seed_otasch_demo.py

Idempotent guard: if the tenant already has students, it does nothing. All money
flows through the normal sales engine (fees -> SalesInvoice -> 4400-class income
accounts; payments -> receipts), so the trial balance stays correct. DEMO DATA —
reset the tenant (reapply COA + education template) before entering real figures.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func, select                                  # noqa: E402
from bizclinik_erp.db import get_session                            # noqa: E402
from bizclinik_erp.models import (Account, BankAccount, Employee,    # noqa: E402
                                  Student, FeeType)
from bizclinik_erp.services import school, school_enrol, school_billing, \
    school_ops, school_staff                                        # noqa: E402
from bizclinik_erp.services.ledger import trial_balance             # noqa: E402

BILL_DATE = date(2025, 9, 15)        # Term 1, 2025/2026 session
ATT_DATE = date(2025, 9, 16)

_FIRST_M = ["Chinedu", "Emeka", "Tunde", "Yusuf", "Femi", "Uche", "Kunle", "Musa", "Obinna", "Segun"]
_FIRST_F = ["Ada", "Ngozi", "Funke", "Amaka", "Aisha", "Chioma", "Bukola", "Halima", "Ifeoma", "Temitope"]
_LAST = ["Okeke", "Adewale", "Bello", "Okonkwo", "Eze", "Mohammed", "Afolabi",
         "Nwosu", "Balogun", "Okafor", "Adeyemi", "Ogunleye", "Lawal", "Obi", "Yakubu"]

# class_code, name, level, per-term tuition, students
_CLASSES = [
    ("KG1", "Kindergarten 1", 0, 40000, 4),
    ("PRY3", "Primary 3", 3, 50000, 6),
    ("JSS1A", "Junior Secondary 1A", 7, 70000, 6),
    ("JSS2A", "Junior Secondary 2A", 8, 75000, 5),
    ("SSS1A", "Senior Secondary 1A", 10, 95000, 5),
]
# code, name, income account, cadence: 'term' (1-3) or 'annual' (0), amount (None=per-class tuition)
_FEES = [
    ("TUI", "Tuition", "4400", "term", None),
    ("EXAM", "Examination", "4420", "term", 5000),
    ("REG", "Registration & Admission", "4410", "annual", 20000),
    ("UNI", "Uniform", "4430", "annual", 15000),
    ("PTA", "PTA / Development Levy", "4470", "annual", 10000),
    # available as fee types for ad-hoc billing, NOT in the auto-bill grid:
    ("TRANS", "Transport / Bus", "4450", "none", 0),
    ("BOARD", "Boarding & Feeding", "4460", "none", 0),
    ("BOOK", "Books & Stationery", "4440", "none", 0),
]
_TEACHERS = [
    ("Grace", "Aderibigbe", "Mathematics"),
    ("Daniel", "Okoro", "English"),
    ("Hauwa", "Sani", "Basic Science"),
    ("Peter", "Olawale", "Social Studies"),
    ("Joy", "Nnamdi", "Primary"),
]


def seed() -> dict:
    with get_session() as s:
        if s.execute(select(func.count()).select_from(Student)).scalar_one() > 0:
            return {"skipped": "OTASCH already has students — demo seed not re-run."}

        # 1. Session + terms
        sess = school.create_academic_session(
            s, session_code="2025/2026", name="2025/2026 Session",
            start_date=date(2025, 9, 1), end_date=date(2026, 7, 31), make_current=True)
        for n, (nm, sd, ed) in enumerate([
                ("First Term", date(2025, 9, 1), date(2025, 12, 12)),
                ("Second Term", date(2026, 1, 6), date(2026, 4, 10)),
                ("Third Term", date(2026, 4, 27), date(2026, 7, 31))], start=1):
            school.create_term(s, academic_session_id=sess.id, term_number=n,
                               name=nm, start_date=sd, end_date=ed)

        # 2. Fee types (wired to education income accounts)
        fee_ids = {}
        for i, (code, name, acct, _cad, _amt) in enumerate(_FEES):
            ft = school.create_fee_type(s, code=code, name=name,
                                       income_account_code=acct, sort_order=i)
            fee_ids[code] = ft.id

        # 3. Teachers (Employees + profiles)
        teacher_ids = []
        for i, (fn, ln, subj) in enumerate(_TEACHERS, start=1):
            emp = Employee(code=f"TCH-{i:03d}", name=f"{fn} {ln}",
                           monthly_gross=180000 + i * 10000, department="Academic",
                           job_title="Teacher", employment_type="full-time")
            s.add(emp); s.flush()
            school_staff.upsert_teacher_profile(
                s, employee_id=emp.id, staff_type="TEACHING",
                qualification="B.Ed", subjects_taught=subj)
            teacher_ids.append(emp.id)

        # 4. Classes (with a form tutor each)
        class_ids = {}
        for i, (code, name, level, _tui, _ns) in enumerate(_CLASSES):
            cls = school.create_school_class(
                s, class_code=code, name=name, form_level=level,
                form_tutor_employee_id=teacher_ids[i % len(teacher_ids)], capacity=40)
            class_ids[code] = cls.id

        # 5. Fee grid — tuition+exam per term, reg/uni/pta annual (one-off)
        for code, name, acct, cad, amt in _FEES:
            if cad == "none":
                continue
            for ccode, _n, _lvl, tui, _ns in _CLASSES:
                value = tui if code == "TUI" else amt
                if cad == "term":
                    for term in (1, 2, 3):
                        school.set_fee_schedule(
                            s, academic_session_id=sess.id, fee_type_id=fee_ids[code],
                            class_id=class_ids[ccode], term_number=term, amount=value)
                else:  # annual / one-off
                    school.set_fee_schedule(
                        s, academic_session_id=sess.id, fee_type_id=fee_ids[code],
                        class_id=class_ids[ccode], term_number=0, amount=value)

        # 6. Students (enrol -> auto-creates a billing Customer each)
        students = []   # (student_id, class_code)
        k = 0
        for ccode, _n, _lvl, _tui, ns in _CLASSES:
            for j in range(ns):
                male = (k % 2 == 0)
                fn = (_FIRST_M if male else _FIRST_F)[k % 10]
                ln = _LAST[k % len(_LAST)]
                stu = school_enrol.enrol_student(
                    s, first_name=fn, last_name=ln, class_id=class_ids[ccode],
                    academic_session_id=sess.id, gender=("M" if male else "F"),
                    guardian_name=f"Mr/Mrs {ln}", guardian_phone=f"080{2000000 + k * 7777}",
                    date_admitted=date(2025, 9, 1))
                students.append((stu.id, ccode))
                k += 1

        # 7. Bill Term 1 (incl. annual one-offs) + a payment mix
        bank_id = s.execute(select(BankAccount.id).order_by(BankAccount.id)).scalars().first()
        billed = paid_full = paid_part = unpaid = 0
        for idx, (sid, _ccode) in enumerate(students):
            b = school_billing.bill_student(
                s, student_id=sid, academic_session_id=sess.id, term_number=1,
                invoice_date=BILL_DATE, include_annual=True, due_date=date(2025, 9, 30))
            if b is None:
                continue
            billed += 1
            bucket = idx % 10
            if bucket < 4:        # ~40% pay in full
                school_billing.record_fee_payment(
                    s, student_id=sid, sales_invoice_id=b.sales_invoice_id,
                    amount=b.total_amount, payment_date=date(2025, 9, 20),
                    bank_account_id=bank_id, reference=f"DEMO-PAY-{idx}")
                paid_full += 1
            elif bucket < 7:      # ~30% partial
                school_billing.record_fee_payment(
                    s, student_id=sid, sales_invoice_id=b.sales_invoice_id,
                    amount=round(b.total_amount * 0.6, 2), payment_date=date(2025, 9, 25),
                    bank_account_id=bank_id, reference=f"DEMO-PAY-{idx}")
                paid_part += 1
            else:                 # ~30% unpaid (defaulters)
                unpaid += 1

        # 8. Attendance for JSS1A on one day
        jss1a = [sid for sid, cc in students if cc == "JSS1A"]
        for i, sid in enumerate(jss1a):
            st = "ABSENT" if i == 1 else ("LATE" if i == 2 else "PRESENT")
            school_ops.record_attendance(
                s, student_id=sid, class_id=class_ids["JSS1A"],
                attendance_date=ATT_DATE, status=st)

        # 9. Results — Maths + English, Term 1, for 3 JSS1A students
        for n, sid in enumerate(jss1a[:3]):
            school_ops.record_result(s, student_id=sid, class_id=class_ids["JSS1A"],
                                     academic_session_id=sess.id, subject="Mathematics",
                                     term_number=1, ca_score=28 + n * 3, exam_score=46 + n * 4,
                                     teacher_employee_id=teacher_ids[0])
            school_ops.record_result(s, student_id=sid, class_id=class_ids["JSS1A"],
                                     academic_session_id=sess.id, subject="English",
                                     term_number=1, ca_score=25 + n * 4, exam_score=40 + n * 5,
                                     teacher_employee_id=teacher_ids[1])

        # 10. Verify + summarise
        tb = trial_balance(s)
        dr = round(sum(r["debit"] for r in tb), 2)
        cr = round(sum(r["credit"] for r in tb), 2)
        dash = school_staff.school_dashboard(s, academic_session_id=sess.id)
        return {
            "session": "2025/2026", "classes": len(_CLASSES),
            "fee_types": len(_FEES), "teachers": len(_TEACHERS),
            "students": len(students), "billed": billed,
            "paid_full": paid_full, "paid_partial": paid_part, "unpaid": unpaid,
            "trial_balance": {"dr": dr, "cr": cr, "balanced": abs(dr - cr) < 0.01},
            "dashboard": dash,
        }


if __name__ == "__main__":
    print(json.dumps(seed(), indent=2, default=str, ensure_ascii=False))
