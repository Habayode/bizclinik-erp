"""Command-line entry point for Trakit365 ERP.

Usage:
    python -m bizclinik_erp <command> [options]

Commands:
    init                       Create tables and seed default COA, tax codes, banks
    reset                      Drop + recreate tables (destructive)
    import-bizclinik <path>    Import a BizClinik xlsx workbook
    trial-balance [--as-of]    Print Trial Balance
    pnl --from --to            Print P&L
    balance-sheet [--as-of]    Print Balance Sheet
    cash-flow --from --to      Print Cash Flow
    ar-aging [--as-of]         AR aging
    ap-aging [--as-of]         AP aging
    vat-return --from --to     VAT return summary
    invoice-pdf <id> <out>     Generate a PDF for invoice id
    list-accounts              Chart of accounts dump
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select

from .config import get_settings
from .db import get_session, init_db, reset_db
from .models import Account, SalesInvoice
from .services import banking, payroll, purchase, reports, sales
from .services.ledger import trial_balance
from .services.tax import vat_return, wht_position


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def _dump(data) -> None:
    def default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)
    json.dump(data, sys.stdout, indent=2, default=default, ensure_ascii=False)
    sys.stdout.write("\n")


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [type YES to confirm]: ").strip() == "YES"


def cmd_init(args) -> int:
    from .services.bootstrap import bootstrap
    pw = getattr(args, "admin_password", None)
    result = bootstrap(admin_password=pw)
    print(f"Initialised {get_settings().db_path}")
    print(f"Admin user: {result['admin_username']}")
    return 0


def cmd_reset(args) -> int:
    if not args.yes and not _confirm("This will DROP all tables and lose data."):
        print("Aborted.")
        return 1
    reset_db()
    from .services.seed import seed_defaults
    with get_session() as s:
        seed_defaults(s)
    print("Database reset and seeded.")
    return 0


def cmd_import(args) -> int:
    from .importers.bizclinik_xlsx import import_workbook
    init_db()
    with get_session() as s:
        summary = import_workbook(s, args.path)
    _dump({k: v for k, v in summary.items() if k != "skipped"})
    if summary.get("skipped"):
        print(f"# {len(summary['skipped'])} rows skipped", file=sys.stderr)
    return 0


def cmd_trial_balance(args) -> int:
    with get_session() as s:
        rows = trial_balance(s, as_of=_parse_date(args.as_of))
    _dump(rows)
    return 0


def cmd_pnl(args) -> int:
    with get_session() as s:
        r = reports.profit_and_loss(
            s, period_start=_parse_date(args.date_from),
            period_end=_parse_date(args.date_to),
        )
    _dump(r)
    return 0


def cmd_balance_sheet(args) -> int:
    as_of = _parse_date(args.as_of) or date.today()
    with get_session() as s:
        r = reports.balance_sheet(s, as_of=as_of)
    _dump(r)
    return 0


def cmd_cash_flow(args) -> int:
    with get_session() as s:
        r = reports.cash_flow(
            s, period_start=_parse_date(args.date_from),
            period_end=_parse_date(args.date_to),
        )
    _dump(r)
    return 0


def cmd_ar_aging(args) -> int:
    as_of = _parse_date(args.as_of) or date.today()
    with get_session() as s:
        _dump(reports.ar_aging(s, as_of=as_of))
    return 0


def cmd_ap_aging(args) -> int:
    as_of = _parse_date(args.as_of) or date.today()
    with get_session() as s:
        _dump(reports.ap_aging(s, as_of=as_of))
    return 0


def cmd_vat_return(args) -> int:
    with get_session() as s:
        _dump({
            "vat": vat_return(s, period_start=_parse_date(args.date_from),
                              period_end=_parse_date(args.date_to)),
            "wht": wht_position(s, period_start=_parse_date(args.date_from),
                                 period_end=_parse_date(args.date_to)),
        })
    return 0


def cmd_invoice_pdf(args) -> int:
    from .exporters.invoice_pdf import write_invoice_pdf
    with get_session() as s:
        out = write_invoice_pdf(s, int(args.invoice_id), args.out)
    print(str(out))
    return 0


def cmd_list_accounts(_args) -> int:
    with get_session() as s:
        rows = [{"code": a.code, "name": a.name, "type": a.type.value,
                  "postable": a.is_postable, "active": a.is_active}
                 for a in s.execute(select(Account).order_by(Account.code)).scalars()]
    _dump(rows)
    return 0


def cmd_tenant_create(args) -> int:
    from .tenancy import create_tenant
    import os
    pw = args.admin_password or os.environ.get("BIZCLINIK_APP_PASSWORD") or "admin"
    t = create_tenant(args.slug, args.name, admin_password=pw)
    print(f"Created tenant {t['slug']} -> {t['db_path']}")
    print("Admin login: username 'admin'")
    return 0


def cmd_tenant_list(_args) -> int:
    from .tenancy import list_tenants
    _dump(list_tenants(active_only=False))
    return 0


def cmd_tenant_adopt(args) -> int:
    """Register a tenant whose DB is a copy of an existing database (migrate
    the original single-tenant books into a named tenant)."""
    from .tenancy import adopt_db_as_tenant
    source = args.source or str(get_settings().db_path)
    t = adopt_db_as_tenant(args.slug, args.name, source)
    print(f"Adopted {source} -> tenant {t['slug']} at {t['db_path']}")
    return 0


def cmd_api_key_create(args) -> int:
    from .tenancy import create_api_key
    key = create_api_key(args.tenant or None, args.label or "")
    print(key)
    print(f"# scope: {args.tenant or 'DEFAULT DB'} — store this now, it is not shown again",
          file=sys.stderr)
    return 0


def cmd_api_key_list(_args) -> int:
    from .tenancy import list_api_keys
    _dump(list_api_keys())
    return 0


def cmd_pg_migrate(_args) -> int:
    """Migrate all SQLite books to PostgreSQL (database-per-tenant).

    Requires BIZCLINIK_DB_BACKEND=postgres + PG* env. Provisions databases,
    copies every table, resets sequences, and verifies row counts. SQLite files
    are left untouched as rollback.
    """
    from .services import pg_migrate
    result = pg_migrate.migrate_all(provision=True)
    if result["created"]:
        print("Created databases:", ", ".join(result["created"]))
    for db in result["databases"]:
        total = sum(db["tables"].values())
        status = "OK" if db["ok"] else "MISMATCH"
        print(f"  [{db['label']:>22}] -> {db['target']:<24} "
              f"{total:>5} rows  {status}")
        for m in db.get("mismatches", []):
            print(f"      ! {m}")
    print("Overall:",
          "OK - counts verified" if result["ok"] else "FAILED - see mismatches")
    return 0 if result["ok"] else 1


def cmd_migrate(_args) -> int:
    """Run the additive schema migration on the default DB and every tenant DB
    so older databases gain columns added to the models since they were made."""
    from . import db as _db
    from .tenancy import list_tenants

    print("Migrating default DB...")
    _db.set_active_db_path(None)
    _db.init_db()

    for t in list_tenants(active_only=False):
        print(f"Migrating tenant {t['slug']} ({t['db_path']})...")
        _db.set_active_db_path(t["db_path"])
        _db.init_db()
    _db.set_active_db_path(None)
    print("Migration complete.")
    return 0


def cmd_harden(_args) -> int:
    """Apply the idempotent production-hardening migrations to the default DB and
    every tenant DB: NUMERIC(18,2) money storage and the journal_line CHECK
    constraints. Postgres-only — a no-op on SQLite. Safe to re-run (each migration
    skips columns/constraints already in place)."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent  # repo root
    rc = 0
    for name, rel in (("decimalize_money", "deploy/migrations/decimalize_money.py"),
                      ("add_ledger_checks", "deploy/migrations/add_ledger_checks.py")):
        path = root / rel
        if not path.exists():
            print(f"(skip {name}: {path} not found)")
            continue
        spec = importlib.util.spec_from_file_location(f"_trakit_harden_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print(f"== {name} ==")
        rc |= int(mod.main(["--all-tenants"]) or 0)
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bizclinik_erp",
                                 description="Trakit365 ERP — CLI")
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Init DB + seed defaults + bootstrap admin")
    p_init.add_argument("--admin-password", help="Optional admin password (defaults to env BIZCLINIK_APP_PASSWORD)")

    p_reset = sub.add_parser("reset", help="DROP + recreate all tables")
    p_reset.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    p_imp = sub.add_parser("import-bizclinik", help="Import BizClinik xlsx")
    p_imp.add_argument("path")

    for name, help_ in [("trial-balance", "Trial Balance"),
                         ("balance-sheet", "Balance Sheet"),
                         ("ar-aging", "AR aging"),
                         ("ap-aging", "AP aging"),
                         ("list-accounts", "List accounts")]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--as-of", help="YYYY-MM-DD")

    for name, help_ in [("pnl", "Profit & Loss"),
                         ("cash-flow", "Cash Flow"),
                         ("vat-return", "VAT return")]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
        sp.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")

    p_pdf = sub.add_parser("invoice-pdf", help="Generate PDF for an invoice id")
    p_pdf.add_argument("invoice_id")
    p_pdf.add_argument("out")

    p_tc = sub.add_parser("tenant-create", help="Register + bootstrap a tenant")
    p_tc.add_argument("slug")
    p_tc.add_argument("name")
    p_tc.add_argument("--admin-password", help="Tenant admin password (default env / 'admin')")

    sub.add_parser("tenant-list", help="List registered tenants")

    p_ta = sub.add_parser("tenant-adopt", help="Adopt an existing DB as a tenant")
    p_ta.add_argument("slug")
    p_ta.add_argument("name")
    p_ta.add_argument("--source", help="Source DB path (default: BIZCLINIK_DB_PATH)")

    p_ak = sub.add_parser("api-key-create", help="Create a REST API key")
    p_ak.add_argument("--tenant", help="Tenant slug (omit for default-DB key)")
    p_ak.add_argument("--label", help="Human label")

    sub.add_parser("api-key-list", help="List API keys (hashes not shown)")

    sub.add_parser("migrate", help="Add missing columns to default + all tenant DBs")
    sub.add_parser("pg-migrate",
                   help="Copy all SQLite books to PostgreSQL (BIZCLINIK_DB_BACKEND=postgres)")
    sub.add_parser("harden",
                   help="Apply idempotent prod-hardening migrations (NUMERIC money "
                        "+ ledger CHECK constraints) to default + all tenant DBs "
                        "(Postgres-only; no-op on SQLite)")

    return p


HANDLERS = {
    "init": cmd_init,
    "reset": cmd_reset,
    "import-bizclinik": cmd_import,
    "trial-balance": cmd_trial_balance,
    "pnl": cmd_pnl,
    "balance-sheet": cmd_balance_sheet,
    "cash-flow": cmd_cash_flow,
    "ar-aging": cmd_ar_aging,
    "ap-aging": cmd_ap_aging,
    "vat-return": cmd_vat_return,
    "invoice-pdf": cmd_invoice_pdf,
    "list-accounts": cmd_list_accounts,
    "tenant-create": cmd_tenant_create,
    "tenant-list": cmd_tenant_list,
    "tenant-adopt": cmd_tenant_adopt,
    "api-key-create": cmd_api_key_create,
    "api-key-list": cmd_api_key_list,
    "migrate": cmd_migrate,
    "pg-migrate": cmd_pg_migrate,
    "harden": cmd_harden,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
