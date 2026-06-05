"""Audit-log service.

Every code path that mutates the books calls `record()`. Keep the call cheap:
just one INSERT per event, no extra queries. Tail it from the GL "Audit log"
page when something looks wrong.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models.audit import AuditAction, AuditLog


def record(
    session: Session,
    *,
    action: AuditAction | str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    description: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    source: Optional[str] = None,
) -> AuditLog:
    """Write one audit row. Returns the persisted entity.

    Caller's responsibility to commit the session (we use the same session as
    the surrounding business operation so the audit row commits atomically
    with the change it describes).
    """
    if isinstance(action, str):
        try:
            action = AuditAction(action)
        except ValueError:
            action = AuditAction.UPDATE  # safe default for unknown verb

    row = AuditLog(
        ts=datetime.utcnow(),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description and description[:512],
        payload_json=json.dumps(payload, default=str) if payload else None,
        user_id=user_id,
        username=username,
        source=source,
    )
    session.add(row)
    session.flush()
    return row


def list_recent(
    session: Session,
    *,
    limit: int = 200,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    user_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
) -> list[AuditLog]:
    q = select(AuditLog).order_by(desc(AuditLog.ts))
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(AuditLog.entity_id == entity_id)
    if user_id is not None:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    q = q.limit(limit)
    return list(session.execute(q).scalars())
