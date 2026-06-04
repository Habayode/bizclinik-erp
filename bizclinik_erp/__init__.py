"""BizClinik ERP — Nigerian SME accounting / ERP system.

Built around a SQLite system-of-record with double-entry general ledger.
Compatible with the original BizClinik xlsx template via an importer.

High-level layout:
    config   — Settings (db path, currency, VAT rate)
    db       — SQLAlchemy engine + session factory
    models   — ORM mapped classes (master + transactional)
    services — Domain logic (ledger, sales, purchase, inventory, banking,
               payroll, tax, reports)
    importers/exporters — BizClinik xlsx in, PDF/xlsx out
    cli      — Command-line entry point (python -m bizclinik_erp)
"""
from .config import Settings, get_settings
from .db import Base, get_session, init_db, reset_db

__all__ = ["Settings", "get_settings", "Base", "get_session", "init_db", "reset_db"]
