"""CLI wrapper around bizclinik_erp.services.backup.

Usage:
    python scripts/backup.py snapshot
    python scripts/backup.py list
    python scripts/backup.py restore <snapshot_path>

The snapshot directory is ``<project_root>/backups``. The live DB path
is taken from BIZCLINIK_DB_PATH (via get_settings()).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


# Make ``bizclinik_erp`` importable when run as a plain script.
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bizclinik_erp.config import get_settings  # noqa: E402
from bizclinik_erp.services import backup as backup_service  # noqa: E402


BACKUP_DIR_NAME = "backups"


def _dest_dir() -> Path:
    return _PROJECT_ROOT / BACKUP_DIR_NAME


def cmd_snapshot(_args: argparse.Namespace) -> int:
    # Snapshot the default DB + control plane + every tenant DB, each into its
    # own subfolder under backups/. In single-tenant installs this is just the
    # default DB.
    results = backup_service.snapshot_all(dest_root=_dest_dir())
    for r in results:
        if "error" in r:
            print(f"  [{r['scope']}] ERROR: {r['error']}")
        else:
            print(f"  [{r['scope']}] {r['snapshot']}"
                  + (f"  (pruned {r['pruned']})" if r.get("pruned") else ""))
    print(f"Backed up {len([r for r in results if 'error' not in r])} database(s).")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    dest = _dest_dir()
    snaps = backup_service.list_snapshots(dest)
    if not snaps:
        print(f"No snapshots in {dest}")
        return 0
    print(f"Snapshots in {dest}:")
    for p in snaps:
        size_mb = p.stat().st_size / (1024 * 1024)
        print(f"  {p.name}  {size_mb:>8.2f} MB")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    settings = get_settings()
    snap = Path(args.path)
    if not snap.is_absolute():
        # try resolving against the backups dir
        candidate = _dest_dir() / snap
        if candidate.exists():
            snap = candidate
    restored = backup_service.restore(snap, settings.db_path)
    print(f"Restored {snap} -> {restored}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backup",
        description="Snapshot / list / restore BizClinik ERP sqlite database.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("snapshot", help="Take a new snapshot and prune old ones.")
    sub.add_parser("list", help="List existing snapshots.")

    p_restore = sub.add_parser("restore", help="Restore a snapshot over the live DB.")
    p_restore.add_argument("path", help="Path to snapshot file (absolute or relative to backups/).")

    return p


HANDLERS = {
    "snapshot": cmd_snapshot,
    "list": cmd_list,
    "restore": cmd_restore,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
