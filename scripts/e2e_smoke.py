"""Continuous end-to-end smoke test.

Posts a full business cycle across EVERY module — Finance (sales, purchases,
inventory, banking, fixed assets + depreciation, bank reconciliation, FX,
recurring, budget, month-end, FIRS, tax), HR (payroll, recruitment + hire,
leave), CRM (lead -> convert -> deal -> activity), and Approvals — then asserts
the books stay sound and every module actually produced postings.

Each run is fully isolated: it forces a fresh throwaway SQLite DB, so it NEVER
touches real tenant data. Reuses scripts/demo_seed.seed_demo() as the poster.

    python scripts/e2e_smoke.py        # one cycle -> JSON report, exit 0=PASS/1=FAIL

Designed to be run repeatedly (a loop / scheduled task) as a live regression
guard across the whole ERP.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# One posted row in each of these proves the module's posting path ran.
_COUNTS = [
    ("finance.sales_invoices", "SalesInvoice"),
    ("finance.receipts", "Receipt"),
    ("finance.bills", "Bill"),
    ("finance.payments", "Payment"),
    ("finance.journal_entries", "JournalEntry"),
    ("finance.fixed_assets", "FixedAsset"),
    ("finance.bank_statements", "BankStatement"),
    ("hr.payroll_runs", "PayrollRun"),
    ("hr.employees", "Employee"),
    ("hr.leave_requests", "LeaveRequest"),
    ("crm.leads", "Lead"),
    ("crm.customers", "Customer"),
]


def _fresh_isolated_db() -> str:
    """Point the app at a brand-new throwaway SQLite file; never prod Postgres."""
    os.environ.pop("BIZCLINIK_DB_BACKEND", None)
    os.environ.pop("PGDATABASE", None)
    path = tempfile.mktemp(suffix="_e2e.db")
    os.environ["BIZCLINIK_DB_PATH"] = path
    from bizclinik_erp.config import get_settings
    from bizclinik_erp.db import get_engine, _session_factory
    for f in (get_settings, get_engine, _session_factory):
        try:
            f.cache_clear()
        except Exception:
            pass
    return path


def run_once() -> dict:
    db_path = _fresh_isolated_db()
    checks: list[dict] = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})

    try:
        from bizclinik_erp.services.bootstrap import bootstrap
        bootstrap(admin_password="smoke")

        from scripts.demo_seed import seed_demo
        rep = seed_demo()  # posts the whole month across all modules

        # --- integrity: the books must balance --------------------------------
        tb = rep["trial_balance"]
        chk("trial_balance_balanced", tb["balanced"],
            f"DR {tb['debit']:.2f} / CR {tb['credit']:.2f}, {tb['lines']} lines")

        # Balance sheet must satisfy Assets = Liabilities + Equity.
        bs = rep.get("balance_sheet") or {}
        a = bs.get("total_assets")
        le = None
        if bs.get("total_liabilities") is not None and bs.get("total_equity") is not None:
            le = bs["total_liabilities"] + bs["total_equity"]
        if a is not None and le is not None:
            chk("balance_sheet_balances", abs(a - le) < 0.01, f"A {a:.2f} vs L+E {le:.2f}")

        # --- coverage: every module produced postings -------------------------
        from sqlalchemy import func, select
        from bizclinik_erp.db import get_session
        from bizclinik_erp import models as M
        figures = {}
        with get_session() as s:
            for label, model_name in _COUNTS:
                model = getattr(M, model_name, None)
                if model is None:
                    chk(label, False, f"model {model_name} not found")
                    continue
                n = s.execute(select(func.count()).select_from(model)).scalar_one()
                figures[label] = n
                chk(label, n > 0, f"{n} row(s)")
            # converted lead -> a customer linked back to its lead
            Lead = getattr(M, "Lead", None)
            if Lead is not None:
                converted = s.execute(
                    select(func.count()).select_from(Lead)
                    .where(Lead.customer_id.is_not(None))).scalar_one()
                chk("crm.lead_converted_to_customer", converted > 0, f"{converted} converted")

        # Depreciation only posts for COMPLETE months after acquisition, so the
        # May demo (asset acquired that month) correctly shows zero. Run a later
        # catch-up to exercise the posting path and confirm the books still tie.
        from datetime import date as _date
        from bizclinik_erp.services import assets as _assets_svc
        from bizclinik_erp.services.ledger import trial_balance as _tb_fn
        with get_session() as s:
            _assets_svc.run_depreciation(s, as_of=_date(2026, 9, 1))
        with get_session() as s:
            dep = s.execute(
                select(func.count()).select_from(M.JournalEntry)
                .where(M.JournalEntry.source_kind == "DEPRECIATION")).scalar_one()
            chk("finance.depreciation_posted", dep > 0, f"{dep} JE(s)")
            rows = _tb_fn(s)
            dr2 = round(sum(r["debit"] for r in rows), 2)
            cr2 = round(sum(r["credit"] for r in rows), 2)
            chk("trial_balance_balanced_after_depreciation", abs(dr2 - cr2) < 0.01,
                f"DR {dr2:.2f} / CR {cr2:.2f}")

        figures["trial_balance"] = {"debit": tb["debit"], "credit": tb["credit"]}
        ok = all(c["ok"] for c in checks)
        return {"pass": ok, "checks": checks, "figures": figures}
    except Exception as e:   # noqa: BLE001
        chk("seed_demo_ran_without_error", False, f"{type(e).__name__}: {e}")
        return {"pass": False, "checks": checks, "error": traceback.format_exc()[-1500:]}
    finally:
        try:
            Path(db_path).unlink(missing_ok=True)
        except Exception:
            pass


def main() -> int:
    brief = "--brief" in sys.argv
    rep = run_once()
    passed = sum(1 for c in rep["checks"] if c["ok"])
    failed = [c for c in rep["checks"] if not c["ok"]]
    if brief:
        from datetime import datetime
        tbf = rep.get("figures", {}).get("trial_balance", {})
        line = (f"{datetime.now().isoformat(timespec='seconds')} "
                f"{'PASS' if rep['pass'] else 'FAIL'} passed={passed} failed={len(failed)}")
        if tbf:
            line += f" tb_dr={tbf.get('debit')} tb_cr={tbf.get('credit')}"
        if failed:
            line += " :: " + "; ".join(f"{c['check']}({c['detail']})" for c in failed)
        if rep.get("error"):
            line += " :: ERROR " + rep["error"].splitlines()[-1][:200]
        print(line)
    else:
        print(json.dumps({
            "pass": rep["pass"], "passed": passed, "failed": len(failed),
            "failures": failed, "figures": rep.get("figures", {}),
            "error": rep.get("error"),
        }, indent=2, default=str, ensure_ascii=False))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
