"""Backfill the journal_line CHECK constraints onto EXISTING databases.

The models declare three CHECK constraints on journal_line (debit>=0, credit>=0,
single-sided), so freshly create_all()'d databases get them. Databases created
before that change (the live Postgres tenants) do not, and ensure_schema() only
does ADD COLUMN — it never adds constraints. This one-shot adds them.

Safe by design:
  * Postgres only (the live backend); SQLite tables can't ALTER ADD CONSTRAINT
    and the legacy single-tenant file relies on the Python guard.
  * Idempotent — skips a constraint that already exists (pg_constraint).
  * Verifies NO existing row violates a constraint before adding it; if any do,
    it SKIPS that constraint and reports, rather than failing the ALTER.
  * Transactional per database.

Usage (run from the repo root, with the Postgres env sourced):
    python deploy/migrations/add_ledger_checks.py --all-tenants [--dry-run]
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from bizclinik_erp.db import get_engine
from bizclinik_erp import tenancy

CONSTRAINTS = [
    ("ck_journal_line_debit_nonneg", "debit >= 0", "debit < 0"),
    ("ck_journal_line_credit_nonneg", "credit >= 0", "credit < 0"),
    ("ck_journal_line_single_sided", "NOT (debit > 0 AND credit > 0)",
     "debit > 0 AND credit > 0"),
]


def _is_postgres(eng) -> bool:
    return eng.dialect.name == "postgresql"


def add_checks_active_db(dry_run: bool = False) -> dict:
    eng = get_engine()
    if not _is_postgres(eng):
        return {"skipped": "not postgres"}
    added, skipped, violated = [], [], []
    with eng.begin() as conn:
        has_tbl = conn.execute(text(
            "SELECT to_regclass('public.journal_line')")).scalar()
        if not has_tbl:
            return {"skipped": "no journal_line table"}
        for name, expr, viol in CONSTRAINTS:
            exists = conn.execute(text(
                "SELECT 1 FROM pg_constraint WHERE conname = :n "
                "AND conrelid = 'public.journal_line'::regclass"), {"n": name}).scalar()
            if exists:
                skipped.append(name)
                continue
            nviol = conn.execute(text(
                f"SELECT count(*) FROM journal_line WHERE {viol}")).scalar()
            if nviol:
                violated.append((name, int(nviol)))
                continue
            if not dry_run:
                conn.execute(text(
                    f'ALTER TABLE journal_line ADD CONSTRAINT {name} CHECK ({expr})'))
            added.append(name)
        if dry_run:
            conn.rollback()
    return {"added": added, "already_present": skipped, "violations": violated}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-tenants", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    results = []
    tenancy.set_active(None)
    r = add_checks_active_db(dry_run=args.dry_run); r["db"] = "default"; results.append(r)
    if args.all_tenants:
        for t in tenancy.list_tenants():
            slug = t["slug"] if isinstance(t, dict) else t.slug
            tenancy.set_active(slug)
            r = add_checks_active_db(dry_run=args.dry_run); r["tenant"] = slug
            results.append(r)
    for r in results:
        print(r)
    if any(r.get("violations") for r in results):
        print("WARNING: some databases have violating rows — those constraints were skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
