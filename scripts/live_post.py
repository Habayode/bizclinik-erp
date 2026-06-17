"""Live continuous poster — posts REAL entries into a live tenant across every
module and sub-feature, then verifies the books still tie.

Unlike e2e_smoke (isolated throwaway DB), this writes into an actual tenant's
database so documents accumulate and exercise the functions for real. Every
identifier is suffixed with a per-run tag, so it can run indefinitely on a
schedule without code collisions.

    python scripts/live_post.py --tenant qa-live            # one cycle (JSON)
    python scripts/live_post.py --tenant qa-live --brief    # one log line

Run with the production env (Postgres) so --tenant resolves to the real tenant
DB. SAFETY: requires --tenant; never posts into the default/legacy DB. Point it
at a dedicated QA tenant, NOT a real customer's books.

Covered: Sales (quotation -> sales order -> invoice -> receipt), Purchases
(bill -> partial payment), Inventory (stock in/out), Banking (charge), GL
(manual journal), Fixed Assets (add + depreciation), Recurring, Budget,
Month-end accrual, FX (rate + revaluation), FIRS e-invoice, CRM (lead ->
convert -> deal -> activity), HR (payroll, recruitment -> hire, leave),
Approvals (gate -> approve).
"""
from __future__ import annotations

import json
import secrets
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func, select                                  # noqa: E402
from bizclinik_erp.db import get_session                            # noqa: E402
from bizclinik_erp.models import (                                  # noqa: E402
    Account, AccountType, BankAccount, Customer, Employee, Product, Supplier,
    DealStage, ActivityKind, RecurringKind, RecurringFrequency,
    ApplicationStage, LeaveType,
)
from bizclinik_erp.services import (                                # noqa: E402
    sales, purchase, payroll, banking, assets, fx, recurring, budget,
    closing, crm, firs, hr as hr_svc, approvals as appr_svc,
)
from bizclinik_erp.services.ledger import post_journal, JELine, trial_balance  # noqa: E402

PS = sales.LineInput
POL = purchase.POLineInput
SLIP = payroll.PayslipInput


def _acct(s, code):
    return s.execute(select(Account).where(Account.code == code)).scalar_one()


def _try(results, name, fn):
    try:
        out = fn()
        results.append({"step": name, "ok": True, "detail": ""})
        return out
    except Exception as e:   # noqa: BLE001
        results.append({"step": name, "ok": False, "detail": f"{type(e).__name__}: {e}"})
        return None


def post_cycle() -> dict:
    """Post one full batch into the ACTIVE tenant. Caller sets the tenant."""
    # Per-run tag, unique even for back-to-back runs (time + random suffix), so
    # codes never collide as the poster runs indefinitely on a schedule.
    tag = datetime.now().strftime("%m%d%H%M%S") + secrets.token_hex(3)
    today = datetime.now().date()
    results: list[dict] = []
    ids: dict = {}

    # ---- master data (unique per run) ---------------------------------------
    def _master():
        with get_session() as s:
            s.add_all([
                Customer(code=f"C-{tag}", name=f"QA Customer {tag}",
                         email=f"c{tag}@qa.local", phone="08000000000"),
                Supplier(code=f"S-{tag}", name=f"QA Supplier {tag}",
                         email=f"s{tag}@qa.local", phone="07000000000"),
                Product(sku=f"P-{tag}", name=f"QA Stock Item {tag}", unit="pc",
                        standard_price=5000, standard_cost=3000, is_stockable=True),
                Product(sku=f"SVC-{tag}", name=f"QA Service {tag}", unit="job",
                        standard_price=8000, standard_cost=0, is_stockable=False),
                Employee(code=f"E-{tag}", name=f"QA Staff {tag}", monthly_gross=150000,
                         department="QA", job_title="Tester", employment_type="full-time"),
            ])
            s.flush()
        with get_session() as s:
            ids["cust"] = s.execute(select(Customer.id).where(Customer.code == f"C-{tag}")).scalar_one()
            ids["supp"] = s.execute(select(Supplier.id).where(Supplier.code == f"S-{tag}")).scalar_one()
            ids["prod"] = s.execute(select(Product.id).where(Product.sku == f"P-{tag}")).scalar_one()
            ids["svc"] = s.execute(select(Product.id).where(Product.sku == f"SVC-{tag}")).scalar_one()
            ids["emp"] = s.execute(select(Employee.id).where(Employee.code == f"E-{tag}")).scalar_one()
            ids["bank"] = s.execute(select(BankAccount.id).order_by(BankAccount.id)).scalars().first()
        return "master ok"
    _try(results, "master_data", _master)
    if "cust" not in ids:
        return {"pass": False, "tag": tag, "steps": results, "tb": None,
                "fatal": "master data failed; aborting cycle"}

    # ---- GL: manual journal (owner capital) ---------------------------------
    def _gl():
        with get_session() as s:
            eq = s.execute(select(Account).where(
                Account.type == AccountType.EQUITY, Account.is_postable == True)).scalars().first()  # noqa: E712
            post_journal(s, today, f"QA capital {tag}", [
                JELine(account_id=_bank_gl(s, ids["bank"]), debit=500000, memo="QA capital"),
                JELine(account_id=eq.id, credit=500000, memo="QA capital"),
            ], source_kind="CAPITAL")
    _try(results, "gl.manual_journal", _gl)

    # ---- Purchases: stock bill + expense bill + partial payment -------------
    def _purchase():
        with get_session() as s:
            b_stock = purchase.receive_bill(
                s, supplier_id=ids["supp"], bill_date=today,
                lines=[POL(product_id=ids["prod"], description="Stock in", qty=100,
                           unit_cost=3000, tax_rate=0.075)],
                due_date=today + timedelta(days=30))
            purchase.receive_bill(
                s, supplier_id=ids["supp"], bill_date=today,
                lines=[POL(product_id=None, description="Rent", qty=1, unit_cost=80000,
                           tax_rate=0.0, expense_account_id=_acct(s, "6200").id)])
            ids["bill_stock"] = b_stock.id
        with get_session() as s:
            purchase.record_payment(s, supplier_id=ids["supp"], payment_date=today,
                                    amount=100000, bank_account_id=ids["bank"],
                                    bill_id=ids["bill_stock"])
    _try(results, "purchase.bill+payment", _purchase)

    # ---- Fixed assets: add + depreciate -------------------------------------
    def _assets():
        with get_session() as s:
            assets.add_asset(s, code=f"FA-{tag}", name=f"QA Asset {tag}",
                             category="Equipment", acquired_date=today - timedelta(days=120),
                             cost=600000, useful_life_months=60,
                             gl_asset_account_id=_acct(s, "1210").id,
                             gl_accum_dep_account_id=_acct(s, "1290").id,
                             gl_dep_expense_account_id=_acct(s, "6600").id,
                             salvage_value=60000)
        with get_session() as s:
            assets.run_depreciation(s, as_of=today)
    _try(results, "assets.add+depreciation", _assets)

    # ---- Sales: quotation -> sales order -> invoice -> partial receipt ------
    def _sales():
        with get_session() as s:
            quo = sales.create_quotation(s, customer_id=ids["cust"], issue_date=today,
                lines=[PS(product_id=ids["prod"], description="Quote", qty=5,
                          unit_price=5000, tax_rate=0.075)])
            so = sales.create_sales_order(s, customer_id=ids["cust"], order_date=today,
                quotation_id=quo.id,
                lines=[PS(product_id=ids["prod"], description="Order", qty=5,
                          unit_price=5000, tax_rate=0.075)])
            inv = sales.issue_invoice(s, customer_id=ids["cust"], invoice_date=today,
                due_date=today + timedelta(days=14),
                lines=[PS(product_id=ids["prod"], description="Goods", qty=10,
                          unit_price=5000, tax_rate=0.075),
                       PS(product_id=ids["svc"], description="Service", qty=1,
                          unit_price=8000, tax_rate=0.075)])
            ids["inv"] = inv.id
        with get_session() as s:
            sales.record_receipt(s, customer_id=ids["cust"], receipt_date=today,
                                 amount=30000, bank_account_id=ids["bank"],
                                 invoice_id=ids["inv"])
    _try(results, "sales.quote+so+invoice+receipt", _sales)

    # ---- Banking: bank charge ----------------------------------------------
    _try(results, "banking.bank_charge", lambda: _bank_charge(ids["bank"], today, tag))

    # ---- Recurring template -------------------------------------------------
    def _recurring():
        with get_session() as s:
            recurring.create_template(s, kind=RecurringKind.INVOICE, code=f"REC-{tag}",
                name=f"QA retainer {tag}", frequency=RecurringFrequency.MONTHLY,
                next_run_date=today + timedelta(days=30),
                payload={"customer_id": ids["cust"], "line_description": "Retainer",
                         "qty": 1, "unit_price": 10000, "tax_rate": 0.075})
    _try(results, "recurring.template", _recurring)

    # ---- Budget + variance --------------------------------------------------
    def _budget():
        with get_session() as s:
            bud = budget.create_budget(s, name=f"QA Budget {tag}", year=today.year)
            budget.set_budget_line(s, bud.id, _acct(s, "6200").id, today.month, 80000)
            budget.budget_vs_actual(s, budget_id=bud.id,
                period_start=today.replace(day=1), period_end=today)
    _try(results, "budget.create+variance", _budget)

    # ---- Month-end accrual (not period close — keep the period open) --------
    def _accrual():
        with get_session() as s:
            closing.accrue_expense(s, on=today, amount=15000,
                                   expense_account_id=_acct(s, "6200").id,
                                   memo=f"QA accrual {tag}")
    _try(results, "closing.accrual", _accrual)

    # ---- FX: set a rate + revalue ------------------------------------------
    def _fx():
        with get_session() as s:
            fx.set_rate(s, "USD", today, 1600.0)
        with get_session() as s:
            fx.unrealized_fx_revaluation(s, as_of=today)
    _try(results, "fx.rate+revaluation", _fx)

    # ---- FIRS e-invoice -----------------------------------------------------
    if ids.get("inv"):
        def _firs():
            with get_session() as s:
                firs.generate_for_invoice(s, ids["inv"])
        _try(results, "firs.einvoice", _firs)

    # ---- CRM: lead -> convert -> deal -> activity ---------------------------
    def _crm():
        with get_session() as s:
            lead = crm.create_lead(s, name=f"QA Lead {tag}", company=f"QA Co {tag}",
                                   source="qa")
            crm.convert_lead(s, lead.id, create_deal=True, deal_amount=250000)
            crm.create_deal(s, title=f"QA Deal {tag}", amount=120000, stage=DealStage.PROPOSAL)
            crm.log_activity(s, subject=f"QA call {tag}", kind=ActivityKind.CALL,
                             due_date=today + timedelta(days=2))
    _try(results, "crm.lead+convert+deal+activity", _crm)

    # ---- HR: payroll --------------------------------------------------------
    def _payroll():
        with get_session() as s:
            payroll.run_payroll(s, period_start=today.replace(day=1), period_end=today,
                                pay_date=today, bank_account_id=ids["bank"],
                                inputs=[SLIP(employee_id=ids["emp"])])
    _try(results, "hr.payroll", _payroll)

    # ---- HR: recruitment -> hire -------------------------------------------
    def _recruit():
        with get_session() as s:
            op = hr_svc.create_opening(s, title=f"QA Role {tag}", department="QA",
                                       location="Lagos", employment_type="full-time")
            cand = hr_svc.add_candidate(s, name=f"QA Candidate {tag}",
                                        email=f"cand{tag}@qa.local", source="qa")
            app = hr_svc.apply(s, opening_id=op.id, candidate_id=cand.id, applied_date=today)
            hr_svc.move_application(s, app.id, ApplicationStage.INTERVIEW)
            hr_svc.hire_candidate(s, app.id, monthly_gross=130000, job_title=f"QA Role {tag}")
    _try(results, "hr.recruitment+hire", _recruit)

    # ---- HR: leave request + approve ---------------------------------------
    def _leave():
        with get_session() as s:
            lr = hr_svc.request_leave(s, employee_id=ids["emp"], leave_type=LeaveType.ANNUAL,
                                      start_date=today + timedelta(days=7),
                                      end_date=today + timedelta(days=9), reason="QA leave")
            hr_svc.decide_leave(s, lr.id, approve=True)
    _try(results, "hr.leave+approve", _leave)

    # ---- Approvals: gate a PO -> approve (no GL impact) ---------------------
    def _approvals():
        with get_session() as s:
            r = appr_svc.gate(s, doc_type="PO", amount=500000.0,
                              title=f"QA PO {tag}",
                              payload={"supplier_id": ids["supp"], "order_date": str(today),
                                       "notes": "QA", "lines": [{"product_id": None,
                                       "description": "QA items", "qty": 1, "unit_cost": 500000,
                                       "tax_rate": 0.0, "expense_account_id": None}]},
                              user_id=None, role="AP")
            appr_svc.approve(s, r["request_id"], approver_user_id=1, approver_role="ACCOUNTANT")
    _try(results, "approvals.gate+approve", _approvals)

    # ---- Integrity: trial balance still ties --------------------------------
    tb = {}
    def _verify():
        with get_session() as s:
            rows = trial_balance(s)
            dr = round(sum(r["debit"] for r in rows), 2)
            cr = round(sum(r["credit"] for r in rows), 2)
            tb.update({"debit": dr, "credit": cr, "balanced": abs(dr - cr) < 0.01})
    _try(results, "verify.trial_balance", _verify)

    ok = all(r["ok"] for r in results) and tb.get("balanced") is True
    return {"pass": ok, "tag": tag, "steps": results, "tb": tb}


def _bank_gl(s, bank_id):
    return s.get(BankAccount, bank_id).gl_account_id


def _bank_charge(bank_id, on, tag):
    with get_session() as s:
        banking.post_bank_charge(s, bank_account_id=bank_id, on=on, amount=1500,
                                 memo=f"QA bank charge {tag}")


def main() -> int:
    argv = sys.argv[1:]
    brief = "--brief" in argv
    tenant = None
    if "--tenant" in argv:
        tenant = argv[argv.index("--tenant") + 1]
    if not tenant:
        print("ERROR: --tenant <slug> is required (never posts into the default DB).")
        return 2
    from bizclinik_erp import tenancy
    if not tenancy.get_tenant(tenant):
        print(f"ERROR: tenant {tenant!r} not found.")
        return 2
    tenancy.set_active(tenant)

    rep = post_cycle()
    failed = [r for r in rep["steps"] if not r["ok"]]
    if brief:
        tb = rep.get("tb") or {}
        line = (f"{datetime.now().isoformat(timespec='seconds')} "
                f"{'PASS' if rep['pass'] else 'FAIL'} tenant={tenant} tag={rep['tag']} "
                f"steps_ok={sum(1 for r in rep['steps'] if r['ok'])}/{len(rep['steps'])} "
                f"tb={'bal' if tb.get('balanced') else 'OFF'}")
        if failed:
            line += " :: " + "; ".join(f"{r['step']}({r['detail']})" for r in failed)
        if rep.get("fatal"):
            line += " :: FATAL " + rep["fatal"]
        print(line)
    else:
        print(json.dumps(rep, indent=2, default=str, ensure_ascii=False))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
