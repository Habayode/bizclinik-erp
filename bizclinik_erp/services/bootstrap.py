"""One-call DB bootstrap: init tables, seed defaults, create admin user."""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from ..db import init_db, get_session
from .seed import seed_defaults
from .users import ensure_bootstrap_admin


def bootstrap(*, admin_password: Optional[str] = None) -> dict:
    """Idempotent: tables → COA + tax codes → first ADMIN user.

    If `admin_password` is None, reads BIZCLINIK_APP_PASSWORD from env. If
    that's also unset, defaults to 'admin' (caller must reset it!).
    """
    init_db()
    pw = admin_password or os.environ.get("BIZCLINIK_APP_PASSWORD") or "admin"
    with get_session() as s:
        seed_defaults(s)
        admin = ensure_bootstrap_admin(s, password=pw)
    return {"admin_username": admin.username, "admin_id": admin.id}
