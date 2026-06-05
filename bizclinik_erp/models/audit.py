"""Audit log table.

Every meaningful mutation (post JE, issue invoice, receive bill, void doc,
period close, user login, etc.) writes one row here. The Streamlit GL page
exposes a viewer.

We keep the schema deliberately narrow — `payload_json` is a TEXT column
that holds whatever context the caller wants (entity snapshot, before/after
diff, request metadata). Querying is mostly by (timestamp, entity_type,
entity_id, user_id, action).
"""
from __future__ import annotations

import enum
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    POST = "POST"          # JE / document posted to ledger
    VOID = "VOID"          # document voided / reversed
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    LOGIN_FAILED = "LOGIN_FAILED"
    CLOSE_PERIOD = "CLOSE_PERIOD"
    LOCK_PERIOD = "LOCK_PERIOD"
    REOPEN_PERIOD = "REOPEN_PERIOD"
    EXPORT = "EXPORT"      # PDF / CSV / report export
    IMPORT = "IMPORT"      # BizClinik xlsx import etc
    BACKUP = "BACKUP"
    RESTORE = "RESTORE"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                          default=datetime.utcnow, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"), index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    # What was acted on.
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    # What happened.
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False, index=True)
    # Optional human-readable summary.
    description: Mapped[Optional[str]] = mapped_column(String(512))
    # Optional structured payload — usually JSON. Use the helper below to
    # serialise; SQLite stores it as TEXT.
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    # Where the action came from (UI page / CLI command / import script).
    source: Mapped[Optional[str]] = mapped_column(String(64))

    def payload(self) -> dict | None:
        if not self.payload_json:
            return None
        try:
            return json.loads(self.payload_json)
        except json.JSONDecodeError:
            return {"_raw": self.payload_json}
