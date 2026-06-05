"""SQLite snapshot / prune / restore for BizClinik ERP.

The database is a single sqlite file in WAL mode. To snapshot safely we
checkpoint the WAL first so the .db file contains every committed page,
then copy the bytes to a timestamped destination.

Functions
---------
snapshot(db_path, dest_dir)         -> Path
    Checkpoint + copy. Returns the snapshot path.
prune(dest_dir, retain_days, retain_min)
    Delete snapshots older than ``retain_days``, but never let the count
    fall below ``retain_min``.
restore(snapshot_path, db_path)
    Overwrite the live db file with a snapshot. The caller MUST stop the
    Streamlit / NSSM service first -- we print a warning either way.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


SNAPSHOT_PREFIX = "bizclinik_"
SNAPSHOT_SUFFIX = ".db"
TIMESTAMP_FMT = "%Y%m%d-%H%M%S"


def _checkpoint(db_path: Path) -> None:
    """Run PRAGMA wal_checkpoint(TRUNCATE) so the .db file is self-contained."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB file not found: {db_path}")
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.commit()
    finally:
        con.close()


def snapshot(db_path: Path, dest_dir: Path) -> Path:
    """Checkpoint the WAL and copy the db file to ``dest_dir``.

    The destination filename is ``bizclinik_{YYYYMMDD-HHMMSS}.db``.
    Returns the absolute path of the new snapshot.
    """
    db_path = Path(db_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    _checkpoint(db_path)
    ts = datetime.now().strftime(TIMESTAMP_FMT)
    dest = dest_dir / f"{SNAPSHOT_PREFIX}{ts}{SNAPSHOT_SUFFIX}"
    shutil.copy2(db_path, dest)
    return dest.resolve()


def list_snapshots(dest_dir: Path) -> list[Path]:
    """Return existing snapshots in ``dest_dir`` sorted oldest -> newest."""
    dest_dir = Path(dest_dir)
    if not dest_dir.exists():
        return []
    snaps = [
        p for p in dest_dir.iterdir()
        if p.is_file()
        and p.name.startswith(SNAPSHOT_PREFIX)
        and p.suffix == SNAPSHOT_SUFFIX
    ]
    snaps.sort(key=lambda p: p.stat().st_mtime)
    return snaps


def prune(
    dest_dir: Path,
    *,
    retain_days: int = 30,
    retain_min: int = 7,
) -> list[Path]:
    """Delete snapshots older than ``retain_days``.

    Will never delete the most recent ``retain_min`` snapshots, even if
    they are older than the cutoff. Returns the list of deleted paths.
    """
    snaps = list_snapshots(dest_dir)
    if len(snaps) <= retain_min:
        return []

    cutoff = datetime.now() - timedelta(days=retain_days)
    cutoff_ts = cutoff.timestamp()

    # Candidates are older than cutoff. Sort newest -> oldest first so we
    # can keep `retain_min` newest and delete the rest of the candidates.
    deletable = [p for p in snaps if p.stat().st_mtime < cutoff_ts]

    # Reserve the newest `retain_min` overall (regardless of age).
    keepers = set(snaps[-retain_min:])
    deleted: list[Path] = []
    for p in deletable:
        if p in keepers:
            continue
        try:
            p.unlink()
            deleted.append(p)
        except OSError as exc:
            print(f"warn: could not delete {p}: {exc}", file=sys.stderr)
    return deleted


def restore(snapshot_path: Path, db_path: Path) -> Path:
    """Overwrite ``db_path`` with the bytes from ``snapshot_path``.

    Best-effort safety: we checkpoint the existing db (if present) so any
    in-flight WAL pages are flushed before we overwrite. The caller is
    expected to have stopped the BizClinikERP service first -- there is
    no way for this function to enforce that.
    """
    snapshot_path = Path(snapshot_path)
    db_path = Path(db_path)

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    print(
        "WARNING: restore() will overwrite the live database. "
        "Stop the BizClinikERP service first (Stop-Service BizClinikERP) "
        "to avoid corrupting an in-flight write.",
        file=sys.stderr,
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        try:
            _checkpoint(db_path)
        except sqlite3.DatabaseError as exc:
            print(f"warn: checkpoint of existing db failed: {exc}", file=sys.stderr)
        # Move the old file aside so the restore is recoverable.
        backup = db_path.with_suffix(db_path.suffix + ".pre_restore")
        shutil.move(str(db_path), str(backup))
        print(f"  Previous db moved to {backup}", file=sys.stderr)

    # Drop stale WAL / SHM files -- they belong to the old database.
    for ext in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + ext)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass

    shutil.copy2(snapshot_path, db_path)
    return db_path.resolve()
