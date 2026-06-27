"""Lightweight additive schema migration for SQLite.

`Base.metadata.create_all()` creates missing *tables* but never adds missing
*columns* to tables that already exist. Every time a model gains a column
(e.g. multi-currency added sales_invoice.currency_code), older databases fall
out of sync and queries fail with "no such column".

`ensure_schema()` closes that gap for additive changes: for each mapped table
that already exists, it compares the model's columns against the live table
and issues `ALTER TABLE ... ADD COLUMN` for anything missing, using the
column's declared default. SQLite supports adding columns with a constant
default, which covers every column we add (all are nullable or defaulted).

This handles ADD COLUMN only — it never drops or retypes columns (safe by
design). Call it after create_all() in init_db().
"""
from __future__ import annotations

import sys
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from ..db import Base


def _default_literal(col) -> Optional[str]:
    """Return a SQL literal for the column's default, or None."""
    d = col.default
    if d is not None and getattr(d, "is_scalar", False):
        val = d.arg
        if isinstance(val, bool):
            # Use the SQL boolean literal, not 1/0. Postgres rejects
            # `BOOLEAN DEFAULT 1` (type mismatch); `true`/`false` is valid on
            # both Postgres and modern SQLite (>= 3.23).
            return "true" if val else "false"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, str):
            return "'" + val.replace("'", "''") + "'"
    # server_default (rare here)
    sd = getattr(col, "server_default", None)
    if sd is not None and getattr(sd, "arg", None) is not None:
        return str(sd.arg)
    return None


def ensure_schema(engine: Optional[Engine] = None) -> list[str]:
    """Add any missing columns to existing tables. Returns the DDL applied."""
    from ..db import get_engine
    eng = engine or get_engine()
    insp = inspect(eng)
    existing_tables = set(insp.get_table_names())
    applied: list[str] = []

    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all() makes brand-new tables
            live_cols = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in live_cols:
                    continue
                coltype = col.type.compile(eng.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                lit = _default_literal(col)
                if lit is not None:
                    ddl += f" DEFAULT {lit}"
                try:
                    conn.execute(text(ddl))
                    applied.append(ddl)
                except Exception as exc:  # pragma: no cover - defensive
                    # Surface loudly: a swallowed ADD COLUMN failure leaves the
                    # live DB out of sync with the model and breaks every query
                    # that loads the table (this once broke login).
                    msg = f"-- FAILED: {ddl}  ({exc})"
                    applied.append(msg)
                    print(f"[ensure_schema] {msg}", file=sys.stderr)

        # Create any indexes declared on the models but missing on existing
        # tables (e.g. the receipt/payment idempotency indexes added later).
        # Best-effort: a pre-existing duplicate would make a UNIQUE index fail,
        # which must not break the deploy — the service-level guard still holds.
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            live_idx = {ix["name"] for ix in insp.get_indexes(table.name)}
            for index in table.indexes:
                if index.name in live_idx:
                    continue
                try:
                    index.create(bind=conn, checkfirst=True)
                    applied.append(f"CREATE INDEX {index.name}")
                except Exception as exc:  # pragma: no cover - defensive
                    applied.append(f"-- FAILED INDEX {index.name}  ({exc})")
    return applied
