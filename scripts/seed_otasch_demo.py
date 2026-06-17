"""Realistic demo data for the OTASCH school tenant — a fully-operating school
you can click through on otasch-erp.hagai.online before the school's real data
lands. Run against the ACTIVE tenant (set otasch active first):

    python scripts/seed_otasch_demo.py

Idempotent guard: if the tenant already has students, it does nothing. Every
money flow goes through the normal engines (fees -> SalesInvoice -> 4400-class
income; receipts; supplier bills -> AP/expense/inventory; payroll), so the trial
balance and the balance sheet stay correct.

What it builds (so every Finance-Dashboard tile is positive, defaulters <=5%):
  - 2025/2026 session + 3 terms; 8 fee types; 5 classes; 12 teachers
  - 150 students (30/class), billed across all 3 terms; ~95% collected so only
    ~5% remain defaulters
  - inventory (5 stockable items) bought from a supplier (-> Inventory + AP)
  - direct costs (cost of uniforms/books sold) and operating expenses (4 months
    of payroll + rent/diesel/materials/exam bills), all dated 2026 and sized
    below revenue so net profit stays positive

DEMO DATA — reset the tenant (reapply COA + education template) before entering
the school's real figures.
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
                                  Product, Student, Supplier)
from bizclinik_erp.services import (school, school_enrol, school_billing,  # noqa: E402
                                    school_ops, school_staff, purchase, payroll,
                                    reports)

ATT_DATE = date(2025, 9, 16)
PER_CLASS = 30          # 5 classes x 30 = 150 students
N_DEFAULTERS = 7        # ~4.7% of 150 (<= 5%)

_FIRST_M = ["Chinedu", "Emeka", "Tunde", "Yusuf", "Femi", "Uche", "Kunle", "Musa",
            "Obinna", "Segun", "Ibrahim", "Chidi", "Bashir", "Tobi", "Ifeanyi",
            "Gbenga", "Sani", "Nnamdi", "Dele", "Kelechi"]
_FIRST_F = ["Ada", "Ngozi", "Funke", "Amaka", "Aisha", "Chioma", "Bukola", "Halima",
            "Ifeoma", "Temitope", "Zainab", "Folake", "Chinyere", "Ronke", "Hauwa",
            "Blessing", "Adaeze", "Yetunde", "Maryam", "Ngozika"]
_LAST = ["Okeke", "Adewale", "Bello", "Okonkwo", "Eze", "Mohammed", "Afolabi",
         "Nwosu", "Balogun", "Okafor", "Adeyemi", "Ogunleye", "Lawal", "Obi",
         "Yakubu", "Danjuma", "Ojo", "Uzoma", "Akpan", "Bamidele", "Igwe"]

# class_code, name, level, per-term tuition
_CLASSES = [
    ("KG1", "Kindergarten 1", 0, 40000),
    ("PRY3", "Primary 3", 3, 50000),
    ("JSS1A", "Junior Secondary 1A", 7, 70000),
    ("JSS2A", "Junior Secondary 2A", 8, 75000),
    ("SSS1A", "Senior Secondary 1A", 10, 95000),
]
# code, name, income account, cadence ('term'|'annual'|'none'), amount (None=tuition)
_FEES = [
    ("TUI", "Tuition", "4400", "term", None),
    ("EXAM", "Examination", "4420", "term", 5000),
    ("REG", "Registration & Admission", "4410", "annual", 20000),
    ("UNI", "Uniform", "4430", "annual", 15000),
    ("PTA", "PTA / Development Levy", "4470", "annual", 10000),
    ("TRANS", "Transport / Bus", "4450", "none", 0),
    ("BOARD", "Boarding & Feeding", "4460", "none", 0),
    ("BOOK", "Books & Stationery", "4440", "none", 0),
]
_TEACHER_NAMES = [
    ("Grace", "Aderibigbe", "Mathematics"), ("Daniel", "Okoro", "English"),
    ("Hauwa", "Sani", "Basic Science"), ("Peter", "Olawale", "Social Studies"),
    ("Joy", "Nnamdi", "Primary"), ("Samuel", "Adeyinka", "Further Maths"),
    ("Fatima", "Bello", "Chemistry"), ("Victor", "Eze", "Physics"),
    ("Rita", "Okafor", "Biology"), ("Ahmed", "Lawal", "Civic Education"),
    ("Esther", "Adeyemi", "Computer Studies"), ("John", "Obi", "Economics"),
]
# stockable inventory: sku, name, unit, price, cost, qty
_INVENTORY = [
    ("UNIFORM", "School Uniform Set", "set", 12000, 8000, 200),
    ("BOOKPK", "Exercise Book Pack", "pack", 2500, 1500, 600),
    ("STAT", "Stationery Pack", "pack", 2000, 1200, 400),
    ("SPORT", "Sports Kit", "set", 7000, 4500, 120),
    ("LAB", "Lab & First-Aid Consumables", "box", 5000, 3000, 80),
]


def _aid(s, code: str):
    return s.execute(select(Account.id).where(Account.code == code)).scalars().first()


def seed() -> dict:
    with get_session() as s:
        if s.execute(select(func.count()).select_from(Student)).scalar_one() > 0:
            return {"skipped": "OTASCH already has students — demo seed not re-run."}

        bank_id = s.execute(select(BankAccount.id).order_by(BankAccount.id)).scalars().first()

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

        # 2. Fee types
        fee_ids = {}
        for i, (code, name, acct, _cad, _amt) in enumerate(_FEES):
            ft = school.create_fee_type(s, code=code, name=name,
                                       income_account_code=acct, sort_order=i)
            fee_ids[code] = ft.id

        # 3. Teachers (Employees + profiles)
        teacher_ids = []
        for i, (fn, ln, subj) in enumerate(_TEACHER_NAMES, start=1):
            emp = Employee(code=f"TCH-{i:03d}", name=f"{fn} {ln}",
                           monthly_gross=180000 + i * 5000, department="Academic",
                           job_title="Teacher", employment_type="full-time")
            s.add(emp); s.flush()
            school_staff.upsert_teacher_profile(
                s, employee_id=emp.id, staff_type="TEACHING",
                qualification="B.Ed", subjects_taught=subj)
            teacher_ids.append(emp.id)

        # 4. Classes
        class_ids = {}
        for i, (code, name, level, _tui) in enumerate(_CLASSES):
            cls = school.create_school_class(
                s, class_code=code, name=name, form_level=level,
                form_tutor_employee_id=teacher_ids[i % len(teacher_ids)], capacity=40)
            class_ids[code] = cls.id

        # 5. Fee grid — tuition+exam per term, reg/uni/pta annual (one-off)
        for code, name, acct, cad, amt in _FEES:
            if cad == "none":
                continue
            for ccode, _n, _lvl, tui in _CLASSES:
                value = tui if code == "TUI" else amt
                terms = (1, 2, 3) if cad == "term" else (0,)
                for term in terms:
                    school.set_fee_schedule(
                        s, academic_session_id=sess.id, fee_type_id=fee_ids[code],
                        class_id=class_ids[ccode], term_number=term, amount=value)

        # 6. Students — 30 per class
        students = []   # (student_id, class_code)
        k = 0
        for ccode, _n, _lvl, _tui in _CLASSES:
            for _j in range(PER_CLASS):
                male = (k % 2 == 0)
                fn = (_FIRST_M if male else _FIRST_F)[k % 20]
                ln = _LAST[(k * 3) % len(_LAST)]
                stu = school_enrol.enrol_student(
                    s, first_name=fn, last_name=ln, class_id=class_ids[ccode],
                    academic_session_id=sess.id, gender=("M" if male else "F"),
                    guardian_name=f"Mr/Mrs {ln}",
                    guardian_phone=f"080{31000000 + k * 131:08d}"[:13],
                    date_admitted=date(2025, 9, 1))
                students.append((stu.id, ccode))
                k += 1

        # 7. Bill all three terms. Collect ~95% in full; the first N_DEFAULTERS
        #    students leave their Term-3 invoice unpaid so the defaulters list and
        #    AR stay meaningful (<=5%).
        defaulter_ids = {students[i][0] for i in range(min(N_DEFAULTERS, len(students)))}
        _TERMS = [   # term, invoice_date, due_date, include_annual, pay_date
            (1, date(2025, 9, 15), date(2025, 9, 30), True,  date(2025, 9, 20)),
            (2, date(2026, 1, 12), date(2026, 1, 31), False, date(2026, 1, 18)),
            (3, date(2026, 4, 28), date(2026, 5, 15), False, date(2026, 5, 6)),
        ]
        billed = paid_full = unpaid = 0
        for term, bdate, due, annual, dpay in _TERMS:
            for sid, _ccode in students:
                b = school_billing.bill_student(
                    s, student_id=sid, academic_session_id=sess.id, term_number=term,
                    invoice_date=bdate, include_annual=annual, due_date=due)
                if b is None:
                    continue
                billed += 1
                if sid in defaulter_ids and term == 3:
                    unpaid += 1            # leave outstanding -> defaulter
                    continue
                school_billing.record_fee_payment(
                    s, student_id=sid, sales_invoice_id=b.sales_invoice_id,
                    amount=b.total_amount, payment_date=dpay,
                    bank_account_id=bank_id, reference=f"PAY-T{term}-{sid}")
                paid_full += 1

        # 8. Suppliers
        def supplier(code, name):
            x = s.execute(select(Supplier).where(Supplier.code == code)).scalars().first()
            if x is None:
                x = Supplier(code=code, name=name); s.add(x); s.flush()
            return x
        edu = supplier("SUP-EDU", "Lagos Edu Supplies Ltd")
        prop = supplier("SUP-PROP", "Ota Properties Ltd")
        pwr = supplier("SUP-PWR", "PowerMax Diesel & Power")

        # 9. Inventory — buy 5 stockable items (DR 1140 / CR AP); left UNPAID -> AP.
        inv_lines = []
        for sku, name, unit, price, cost, qty in _INVENTORY:
            p = Product(sku=sku, name=name, unit=unit, standard_price=price,
                        standard_cost=cost, is_stockable=True, is_active=True)
            s.add(p); s.flush()
            inv_lines.append(purchase.POLineInput(product_id=p.id,
                              description=f"{name} (opening stock)", qty=qty, unit_cost=cost))
        purchase.receive_bill(s, supplier_id=edu.id, bill_date=date(2026, 2, 5),
                              due_date=date(2026, 3, 5), lines=inv_lines)

        # 10. Direct costs (cost of uniforms/books sold), paid.
        for acct, amt, when, desc in [
                ("5300", 700000, date(2026, 3, 15), "Cost of uniforms sold to pupils"),
                ("5310", 500000, date(2026, 4, 15), "Cost of books & stationery sold")]:
            bl = purchase.receive_bill(s, supplier_id=edu.id, bill_date=when, due_date=when,
                lines=[purchase.POLineInput(product_id=None, description=desc, qty=1,
                       unit_cost=amt, expense_account_id=_aid(s, acct))])
            purchase.record_payment(s, supplier_id=edu.id, payment_date=when,
                amount=bl.grand_total, bank_account_id=bank_id, bill_id=bl.id,
                reference=f"PAY-{bl.number}")

        # 11. Operating expenses — rent/diesel/materials/exam bills (pay all but
        #     June rent -> AP) + 4 monthly payroll runs (salaries -> 6100, PAYE).
        month_end = [(2, 28), (3, 31), (4, 30), (5, 31), (6, 30)]
        rent, diesel = [], []
        for m, d in month_end:
            rent.append(purchase.receive_bill(s, supplier_id=prop.id, bill_date=date(2026, m, d),
                due_date=date(2026, m, d), lines=[purchase.POLineInput(product_id=None,
                description=f"Premises rent & utilities {m}/2026", qty=1, unit_cost=350000,
                expense_account_id=_aid(s, "6200"))]))
            diesel.append(purchase.receive_bill(s, supplier_id=pwr.id, bill_date=date(2026, m, d),
                due_date=date(2026, m, d), lines=[purchase.POLineInput(product_id=None,
                description=f"Diesel & generator fuel {m}/2026", qty=1, unit_cost=220000,
                expense_account_id=_aid(s, "6300"))]))
        mat = purchase.receive_bill(s, supplier_id=edu.id, bill_date=date(2026, 3, 20),
            due_date=date(2026, 4, 5), lines=[purchase.POLineInput(product_id=None,
            description="Teaching materials & supplies", qty=1, unit_cost=500000,
            expense_account_id=_aid(s, "6800"))])
        exam = purchase.receive_bill(s, supplier_id=edu.id, bill_date=date(2026, 5, 20),
            due_date=date(2026, 6, 5), lines=[purchase.POLineInput(product_id=None,
            description="Examination expenses (T2/T3)", qty=1, unit_cost=400000,
            expense_account_id=_aid(s, "6810"))])
        for bl in rent[:-1] + diesel + [mat, exam]:   # all but June rent
            purchase.record_payment(s, supplier_id=bl.supplier_id, payment_date=bl.bill_date,
                amount=bl.grand_total, bank_account_id=bank_id, bill_id=bl.id,
                reference=f"PAY-{bl.number}")

        slips = [payroll.PayslipInput(employee_id=t) for t in teacher_ids]
        for m, d in [(2, 28), (3, 31), (4, 30), (5, 31)]:
            payroll.run_payroll(s, period_start=date(2026, m, 1), period_end=date(2026, m, d),
                pay_date=date(2026, m, d), inputs=slips, bank_account_id=bank_id,
                notes=f"Staff salaries {m}/2026")

        # 12. Attendance (JSS1A, one day) + a few results
        jss1a = [sid for sid, cc in students if cc == "JSS1A"]
        for i, sid in enumerate(jss1a):
            stt = "ABSENT" if i == 1 else ("LATE" if i == 2 else "PRESENT")
            school_ops.record_attendance(s, student_id=sid, class_id=class_ids["JSS1A"],
                                         attendance_date=ATT_DATE, status=stt)
        for n, sid in enumerate(jss1a[:5]):
            school_ops.record_result(s, student_id=sid, class_id=class_ids["JSS1A"],
                academic_session_id=sess.id, subject="Mathematics", term_number=1,
                ca_score=28 + n * 2, exam_score=46 + n * 3, teacher_employee_id=teacher_ids[0])
            school_ops.record_result(s, student_id=sid, class_id=class_ids["JSS1A"],
                academic_session_id=sess.id, subject="English", term_number=1,
                ca_score=25 + n * 3, exam_score=40 + n * 4, teacher_employee_id=teacher_ids[1])

        # 13. Verify + summarise (FY2026 P&L; balance sheet as at year-end)
        as_of = date(2026, 12, 31)
        pnl = reports.profit_and_loss(s, period_start=date(2026, 1, 1), period_end=as_of)
        bs = reports.balance_sheet(s, as_of=as_of)
        ar = reports.ar_aging(s, as_of=as_of)
        ap = reports.ap_aging(s, as_of=as_of)
        inv140 = round(sum(r["amount"] for r in bs["assets"] if r["code"] == "1140"), 2)
        dash = school_staff.school_dashboard(s, academic_session_id=sess.id)
        return {
            "session": "2025/2026", "classes": len(_CLASSES),
            "fee_types": len(_FEES), "teachers": len(teacher_ids),
            "students": len(students), "billed": billed,
            "paid_full": paid_full, "unpaid": unpaid,
            "defaulter_count": dash["defaulter_count"],
            "revenue": pnl["total_revenue"], "direct_costs": pnl["total_direct_costs"],
            "operating_expenses": pnl["total_operating_expenses"],
            "net_profit": pnl["net_profit"],
            "inventory_value": inv140,
            "ar_outstanding": round(sum(r["total"] for r in ar), 2),
            "ap_outstanding": round(sum(r["total"] for r in ap), 2),
            "balance_sheet_balanced": bs["balanced"],
            "dashboard": dash,
        }


if __name__ == "__main__":
    print(json.dumps(seed(), indent=2, default=str, ensure_ascii=False))
