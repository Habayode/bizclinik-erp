"""Case-study seed: GreenLeaf Stores Ltd — a full month (May 2026) across every module.

Posts onboarding + a realistic month of transactions for a Lagos retail + delivery
SME, then runs every report. Returns a structured dict so the user manual can quote
REAL figures (not invented ones). Run against a fresh DB or an active tenant context.

    python scripts/demo_seed.py            # prints a JSON summary

The script is deterministic (fixed dates/amounts) so the manual stays reproducible.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select                                        # noqa: E402
from bizclinik_erp.db import get_session                            # noqa: E402
from bizclinik_erp.models import (                                  # noqa: E402
    Account, AccountType, BankAccount, Company, Customer, Employee, Product,
    Supplier, DealStage, ActivityKind, RecurringKind, RecurringFrequency,
)
from bizclinik_erp.services import (                                # noqa: E402
    sales, purchase, payroll, banking, recon, assets, fx, recurring,
    budget, closing, crm, firs, tax, reports, invoice_template,
)
from bizclinik_erp.services.ledger import trial_balance             # noqa: E402

PS = sales.LineInput
POL = purchase.POLineInput
SLIP = payroll.PayslipInput


def _acct(s, code):
    return s.execute(select(Account).where(Account.code == code)).scalar_one()


def _bank(s, code):
    return s.execute(select(BankAccount).where(BankAccount.code == code)).scalar_one()


def seed_demo() -> dict:
    from bizclinik_erp.services.bootstrap import bootstrap
    # Bootstrap creates tables + seeds COA / tax / banks / FX.
    bootstrap(admin_password="GreenLeaf#2026")

    # ---- 1. Company profile -------------------------------------------------
    with get_session() as s:
        co = s.query(Company).first()
        if not co:
            co = Company(name="GreenLeaf Stores Ltd"); s.add(co)
        co.name = "GreenLeaf Stores Ltd"
        co.rc_number = "RC 1843022"
        co.tin = "TIN-20471188-0001"
        co.address = "14 Adeniyi Jones Avenue, Ikeja, Lagos"
        co.email = "accounts@greenleafstores.ng"
        co.phone = "+234 803 555 0142"
        co.vat_number = "TIN-20471188-0001"
        # Branding for invoices.
        invoice_template.update(s, accent_color="#0A7D33",
                                payment_instructions="GTBank 0123456789 — GreenLeaf Stores Ltd",
                                thank_you_note="Thank you for shopping with GreenLeaf!",
                                footer_note="GreenLeaf Stores Ltd · RC 1843022 · Ikeja, Lagos")

    # ---- 2. Master data -----------------------------------------------------
    with get_session() as s:
        s.add_all([
            Customer(code="C001", name="Sunrise Restaurant Ltd", email="pay@sunrise.ng", phone="08030001111", address="5 Allen Ave, Ikeja"),
            Customer(code="C002", name="Mama Tobi Kitchen", email="mamatobi@mail.ng", phone="08030002222", address="22 Opebi Rd, Ikeja"),
            Customer(code="C003", name="Adeyemi Household", email="ade@mail.ng", phone="08030003333", address="9 Magodo Estate"),
            Customer(code="C004", name="Global Imports LLC (US)", email="ap@globalimports.com", phone="+1 202 555 0190", address="Houston, TX, USA"),
        ])
        s.add_all([
            Supplier(code="S001", name="FreshFarm Produce Ltd", email="sales@freshfarm.ng", phone="07010001111"),
            Supplier(code="S002", name="PackRight Supplies", email="orders@packright.ng", phone="07010002222"),
            Supplier(code="S003", name="Lagos Properties Ltd", email="rent@lagosprop.ng", phone="07010003333"),
        ])
        s.add_all([
            Product(sku="RICE50", name="Rice 50kg Bag", unit="bag", standard_price=45000, standard_cost=38000, is_stockable=True),
            Product(sku="OIL25", name="Vegetable Oil 25L", unit="keg", standard_price=33000, standard_cost=28000, is_stockable=True),
            Product(sku="CARTON", name="Packaging Carton", unit="pc", standard_price=1800, standard_cost=1200, is_stockable=True),
            Product(sku="DELIV", name="Delivery Service", unit="trip", standard_price=5000, standard_cost=0, is_stockable=False),
        ])
        s.add_all([
            Employee(code="E001", name="Chioma Okeke", monthly_gross=250000,
                     department="Operations", job_title="Store Manager",
                     employment_type="full-time"),
            Employee(code="E002", name="Bola Adewale", monthly_gross=180000,
                     department="Sales", job_title="Sales Associate",
                     employment_type="full-time"),
            Employee(code="E003", name="Emeka Driver", monthly_gross=120000,
                     department="Logistics", job_title="Delivery Driver",
                     employment_type="full-time"),
        ])
        s.flush()

    ids = {}
    with get_session() as s:
        for c in s.query(Customer).all(): ids[c.code] = c.id
        for sup in s.query(Supplier).all(): ids[sup.code] = sup.id
        for p in s.query(Product).all(): ids[p.sku] = p.id
        for e in s.query(Employee).all(): ids[e.code] = e.id
        bank1 = _bank(s, "BANK1").id
        equity = s.execute(select(Account).where(Account.type == AccountType.EQUITY, Account.is_postable == True)).scalars().first()  # noqa: E712
        equity_id = equity.id
        eq_code = equity.code
        rent_acct = _acct(s, "6200").id
        mkt_acct = _acct(s, "6400").id

    # ---- 3. Opening capital (owner injects funds) ---------------------------
    from bizclinik_erp.services.ledger import post_journal, JELine
    with get_session() as s:
        post_journal(s, date(2026, 5, 1), "Owner capital injection", [
            JELine(account_id=_bank(s, "BANK1").gl_account_id, debit=5_000_000, memo="Capital"),
            JELine(account_id=equity_id, credit=5_000_000, memo="Capital"),
        ], source_kind="CAPITAL")

    # ---- 4. Purchases: stock in + equipment + rent --------------------------
    bills = {}
    with get_session() as s:
        b1 = purchase.receive_bill(s, supplier_id=ids["S001"], bill_date=date(2026, 5, 2),
            lines=[POL(product_id=ids["RICE50"], description="Rice 50kg x40", qty=40, unit_cost=38000, tax_rate=0.075),
                   POL(product_id=ids["OIL25"], description="Veg Oil 25L x30", qty=30, unit_cost=28000, tax_rate=0.075)],
            due_date=date(2026, 5, 30))
        b2 = purchase.receive_bill(s, supplier_id=ids["S002"], bill_date=date(2026, 5, 3),
            lines=[POL(product_id=ids["CARTON"], description="Cartons x500", qty=500, unit_cost=1200, tax_rate=0.075)],
            due_date=date(2026, 5, 25))
        # Equipment purchase -> Fixed asset account 1210 (non-stock line)
        b3 = purchase.receive_bill(s, supplier_id=ids["S002"], bill_date=date(2026, 5, 3),
            lines=[POL(product_id=None, description="Cold-room freezer", qty=1, unit_cost=1_800_000, tax_rate=0.0,
                       expense_account_id=_acct(s, "1210").id)])
        # Rent (expense)
        b4 = purchase.receive_bill(s, supplier_id=ids["S003"], bill_date=date(2026, 5, 1),
            lines=[POL(product_id=None, description="Shop rent — May", qty=1, unit_cost=350000, tax_rate=0.0,
                       expense_account_id=rent_acct)], due_date=date(2026, 5, 5))
        bills = {"stock1": b1.id, "stock2": b2.id, "equip": b3.id, "rent": b4.id}

    # ---- 5. Register the fixed asset + pay rent/supplier ---------------------
    with get_session() as s:
        assets.add_asset(s, code="FA-001", name="Cold-room Freezer", category="Equipment",
            acquired_date=date(2026, 5, 3), cost=1_800_000, useful_life_months=60,
            gl_asset_account_id=_acct(s, "1210").id,
            gl_accum_dep_account_id=_acct(s, "1290").id,
            gl_dep_expense_account_id=_acct(s, "6600").id, salvage_value=300_000)
    with get_session() as s:
        purchase.record_payment(s, supplier_id=ids["S003"], payment_date=date(2026, 5, 4),
                                amount=350000, bank_account_id=bank1, bill_id=bills["rent"])
        purchase.record_payment(s, supplier_id=ids["S001"], payment_date=date(2026, 5, 20),
                                amount=2_000_000, bank_account_id=bank1, bill_id=bills["stock1"])

    # ---- 6. Sales: NGN invoices + 1 USD export ------------------------------
    fx.set_rate_present = True
    with get_session() as s:
        fx.set_rate(s, "USD", date(2026, 5, 1), 1550.0)
    inv = {}
    with get_session() as s:
        inv["i1"] = sales.issue_invoice(s, customer_id=ids["C001"], invoice_date=date(2026, 5, 6),
            due_date=date(2026, 5, 20),
            lines=[PS(product_id=ids["RICE50"], description="Rice 50kg x10", qty=10, unit_price=45000, tax_rate=0.075),
                   PS(product_id=ids["DELIV"], description="Delivery", qty=1, unit_price=5000, tax_rate=0.075)]).id
        inv["i2"] = sales.issue_invoice(s, customer_id=ids["C002"], invoice_date=date(2026, 5, 10),
            due_date=date(2026, 5, 24),
            lines=[PS(product_id=ids["OIL25"], description="Veg Oil 25L x8", qty=8, unit_price=33000, tax_rate=0.075)]).id
        inv["i3"] = sales.issue_invoice(s, customer_id=ids["C003"], invoice_date=date(2026, 5, 15),
            lines=[PS(product_id=ids["RICE50"], description="Rice 50kg x2", qty=2, unit_price=45000, tax_rate=0.075),
                   PS(product_id=ids["CARTON"], description="Cartons x20", qty=20, unit_price=1800, tax_rate=0.075)]).id
        # USD export
        inv["i4"] = sales.issue_invoice(s, customer_id=ids["C004"], invoice_date=date(2026, 5, 18),
            currency_code="USD", due_date=date(2026, 6, 18),
            lines=[PS(product_id=ids["OIL25"], description="Veg Oil export x10", qty=10, unit_price=25, tax_rate=0.0)]).id

    # ---- 7. Receipts --------------------------------------------------------
    with get_session() as s:
        sales.record_receipt(s, customer_id=ids["C001"], receipt_date=date(2026, 5, 19),
                             amount=inv_total(s, inv["i1"]), bank_account_id=bank1, invoice_id=inv["i1"])
        sales.record_receipt(s, customer_id=ids["C002"], receipt_date=date(2026, 5, 22),
                             amount=inv_total(s, inv["i2"]), bank_account_id=bank1, invoice_id=inv["i2"])

    # ---- 8. Marketing expense bill + bank charge ----------------------------
    with get_session() as s:
        purchase.receive_bill(s, supplier_id=ids["S002"], bill_date=date(2026, 5, 12),
            lines=[POL(product_id=None, description="Radio advert", qty=1, unit_cost=120000, tax_rate=0.0,
                       expense_account_id=mkt_acct)])
        banking.post_bank_charge(s, bank_account_id=bank1, on=date(2026, 5, 30), amount=2500,
                                 memo="Account maintenance")

    # ---- 9. Payroll (June) --------------------------------------------------
    with get_session() as s:
        payroll.run_payroll(s, period_start=date(2026, 5, 1), period_end=date(2026, 5, 30),
            pay_date=date(2026, 5, 28), bank_account_id=bank1,
            inputs=[SLIP(employee_id=ids["E001"]), SLIP(employee_id=ids["E002"]), SLIP(employee_id=ids["E003"])])

    # ---- 10. Depreciation (month-end) --------------------------------------
    with get_session() as s:
        assets.run_depreciation(s, as_of=date(2026, 5, 30))

    # ---- 11. Bank reconciliation -------------------------------------------
    with get_session() as s:
        stmt = recon.create_statement(s, bank_account_id=bank1, period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 30), opening_balance=0, closing_balance=0, source_file="GTBank-June.csv")
        recon.import_statement_lines(s, stmt.id, [
            {"txn_date": date(2026, 5, 1), "description": "Capital", "amount": 5_000_000, "reference": "CAP"},
            {"txn_date": date(2026, 5, 4), "description": "Rent paid", "amount": -350000, "reference": "RENT"},
            {"txn_date": date(2026, 5, 19), "description": "Sunrise receipt", "amount": inv_total_ro(s, inv["i1"]), "reference": "RCP1"},
            {"txn_date": date(2026, 5, 30), "description": "Bank charge", "amount": -2500, "reference": "CHG"},
        ])
        recon.auto_match(s, stmt.id)
        recon_summary = recon.reconciliation_summary(s, stmt.id)

    # ---- 12. Unrealized FX, recurring, budget, accrual, CRM, FIRS -----------
    with get_session() as s:
        fx.set_rate(s, "USD", date(2026, 5, 30), 1600.0)
        fx_rev = fx.unrealized_fx_revaluation(s, as_of=date(2026, 5, 30))
    with get_session() as s:
        recurring.create_template(s, kind=RecurringKind.INVOICE, code="REC-RENT-INV",
            name="Monthly retainer — Sunrise", frequency=RecurringFrequency.MONTHLY,
            next_run_date=date(2026, 6, 1),
            payload={"customer_id": ids["C001"], "line_description": "Monthly supply retainer",
                     "qty": 1, "unit_price": 150000, "tax_rate": 0.075})
    with get_session() as s:
        bud = budget.create_budget(s, name="FY2026 Operating Budget", year=2026)
        budget.set_budget_line(s, bud.id, _acct(s, "6100").id, 5, 600000)   # salaries
        budget.set_budget_line(s, bud.id, _acct(s, "6200").id, 5, 350000)   # rent
        budget.set_budget_line(s, bud.id, _acct(s, "6400").id, 5, 100000)   # marketing
        bva = budget.budget_vs_actual(s, budget_id=bud.id,
                                      period_start=date(2026, 5, 1), period_end=date(2026, 5, 30))
    with get_session() as s:
        closing.accrue_expense(s, on=date(2026, 5, 30), amount=45000,
                               expense_account_id=_acct(s, "6200").id, memo="June utilities (estimated)")
        checklist = closing.close_checklist(s, year=2026, month=5)
    with get_session() as s:
        l1 = crm.create_lead(s, name="Tunde Bakare", company="TB Mega Foods", email="tunde@tbmega.ng", source="referral")
        crm.convert_lead(s, l1.id, create_deal=True, deal_amount=900000)
        crm.create_lead(s, name="Ada Eze", company="Eze Catering", source="web")
        crm.create_deal(s, title="Eze Catering — supply contract", amount=450000, stage=DealStage.PROPOSAL)
        crm.log_activity(s, subject="Call Tunde re: contract", kind=ActivityKind.CALL, due_date=date(2026, 6, 2))
        crm_pipe = crm.pipeline_summary(s)
    with get_session() as s:
        firs_sub = firs.generate_for_invoice(s, inv["i1"])
        firs_irn = firs_sub.irn

    # ---- 12b. HR (recruitment + leave) and Approvals demo --------------------
    # NOTE: deliberately ledger-neutral — the only approval that gets APPROVED
    # is a purchase order (no GL impact), the over-limit bill stays PENDING and
    # the third request is REJECTED, so May's verified figures don't change.
    from bizclinik_erp.services import hr as hr_svc
    from bizclinik_erp.services import approvals as appr_svc
    from bizclinik_erp.models import ApplicationStage, LeaveType
    with get_session() as s:
        # Recruitment: one open role mid-pipeline, one filled by a hire.
        op1 = hr_svc.create_opening(s, title="Store Cashier", department="Retail",
                                    location="Ikeja, Lagos", employment_type="full-time",
                                    description="Front-desk cashier for the Ikeja store.")
        op2 = hr_svc.create_opening(s, title="Warehouse Assistant", department="Logistics",
                                    location="Ikeja, Lagos", employment_type="contract")
        c1 = hr_svc.add_candidate(s, name="Chidi Nwosu", email="chidi.n@mail.ng",
                                  phone="0803 222 1100", source="job board")
        c2 = hr_svc.add_candidate(s, name="Funke Adebayo", email="funke.a@mail.ng",
                                  source="referral")
        a1 = hr_svc.apply(s, opening_id=op1.id, candidate_id=c1.id,
                          applied_date=date(2026, 5, 20))
        hr_svc.move_application(s, a1.id, ApplicationStage.INTERVIEW)
        a2 = hr_svc.apply(s, opening_id=op2.id, candidate_id=c2.id,
                          applied_date=date(2026, 5, 15))
        hr_svc.hire_candidate(s, a2.id, monthly_gross=95000,
                              job_title="Warehouse Assistant")
        # Leave: one approved (reduces balance), one pending.
        emp_ids = {e.code: e.id for e in hr_svc.list_employees(s)}
        lr1 = hr_svc.request_leave(s, employee_id=emp_ids["E001"],
                                   leave_type=LeaveType.ANNUAL,
                                   start_date=date(2026, 6, 8), end_date=date(2026, 6, 12),
                                   reason="Family travel")
        hr_svc.decide_leave(s, lr1.id, approve=True)
        hr_svc.request_leave(s, employee_id=emp_ids["E002"],
                             leave_type=LeaveType.SICK,
                             start_date=date(2026, 6, 3), end_date=date(2026, 6, 4),
                             reason="Medical")
        # Approvals: one APPROVED PO (no GL), one PENDING bill, one REJECTED.
        sup_ids = {x.code: x.id for x in s.query(Supplier).all()}
        po_payload = {"supplier_id": sup_ids["S002"], "order_date": "2026-06-02",
                      "notes": "June restock commitment",
                      "lines": [{"product_id": None, "description": "Cartons restock",
                                 "qty": 300, "unit_cost": 1200, "tax_rate": 0.075,
                                 "expense_account_id": None}]}
        r_ok = appr_svc.gate(s, doc_type="PO", amount=387_000.0,
                             title="PO — PackRight Supplies (₦387,000)",
                             payload=po_payload, user_id=None, role="AP")
        appr_svc.approve(s, r_ok["request_id"], approver_user_id=1,
                         approver_role="ACCOUNTANT")
        exp_row = s.execute(
            select(Account).where(Account.code == "6300")).scalar_one_or_none()
        exp_acct = exp_row.id if exp_row else None
        bill_payload = {"supplier_id": sup_ids["S001"], "bill_date": "2026-06-05",
                        "due_date": "2026-07-05", "currency_code": "NGN",
                        "fx_rate": None, "notes": "June bulk restock",
                        "lines": [{"product_id": None, "description": "Rice 50kg x 15",
                                   "qty": 15, "unit_cost": 40000, "tax_rate": 0.075,
                                   "expense_account_id": exp_acct}]}
        appr_svc.gate(s, doc_type="BILL", amount=645_000.0,
                      title="Bill — FreshFarm Produce (₦645,000)",
                      payload=bill_payload, user_id=None, role="AP")  # stays PENDING
        r_no = appr_svc.gate(s, doc_type="PAYMENT", amount=300_000.0,
                             title="Payment — PackRight advance (₦300,000)",
                             payload={"supplier_id": sup_ids["S002"],
                                      "payment_date": "2026-06-06", "amount": 300000,
                                      "bank_account_id": _bank(s, "BANK1").id,
                                      "bill_id": None, "method": "BANK",
                                      "reference": None, "settlement_fx_rate": None},
                             user_id=None, role="AP")
        appr_svc.reject(s, r_no["request_id"], approver_user_id=1,
                        approver_role="ACCOUNTANT", note="Not budgeted — defer to July")
        hr_summary = {"recruitment": hr_svc.recruitment_summary(s),
                      "leave": hr_svc.leave_summary(s),
                      "pending_approvals": appr_svc.pending_count(s)}

    # ---- 13. Reports --------------------------------------------------------
    with get_session() as s:
        tb = trial_balance(s)
        pnl = reports.profit_and_loss(s, period_start=date(2026, 5, 1), period_end=date(2026, 5, 30))
        bs = reports.balance_sheet(s, as_of=date(2026, 5, 30))
        cf = reports.cash_flow(s, period_start=date(2026, 5, 1), period_end=date(2026, 5, 30))
        ar = reports.ar_aging(s, as_of=date(2026, 5, 30))
        ap = reports.ap_aging(s, as_of=date(2026, 5, 30))
        vat = tax.vat_return(s, period_start=date(2026, 5, 1), period_end=date(2026, 5, 30))
        wht = tax.wht_position(s, period_start=date(2026, 5, 1), period_end=date(2026, 5, 30))
        tb_dr = round(sum(r["debit"] for r in tb), 2)
        tb_cr = round(sum(r["credit"] for r in tb), 2)

    return {
        "company": "GreenLeaf Stores Ltd",
        "period": "May 2026",
        "trial_balance": {"debit": tb_dr, "credit": tb_cr, "balanced": abs(tb_dr - tb_cr) < 0.01, "lines": len(tb)},
        "profit_and_loss": pnl,
        "balance_sheet": bs,
        "cash_flow": cf,
        "ar_aging": ar,
        "ap_aging": ap,
        "vat_return": vat,
        "wht_position": wht,
        "bank_reconciliation": recon_summary,
        "unrealized_fx": fx_rev.get("net_unrealized"),
        "budget_vs_actual": bva,
        "month_end_checklist": checklist,
        "crm_pipeline": crm_pipe,
        "firs_irn": firs_irn,
        "hr_approvals": hr_summary,
    }


def inv_total(s, invoice_id):
    from bizclinik_erp.models import SalesInvoice
    return s.get(SalesInvoice, invoice_id).grand_total


def inv_total_ro(s, invoice_id):
    return inv_total(s, invoice_id)


if __name__ == "__main__":
    rep = seed_demo()
    def default(o):
        try:
            return float(o)
        except Exception:
            return str(o)
    print(json.dumps(rep, indent=2, default=default, ensure_ascii=False))
