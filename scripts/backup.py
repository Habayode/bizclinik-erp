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
import os
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

    # Push offsite to R2 if configured. Non-fatal: the local snapshot still
    # succeeded even if the offsite leg is unconfigured or fails.
    if not getattr(_args, "no_offsite", False):
        _offsite_push(soft=True)
    return 0


def _offsite_push(*, soft: bool) -> int:
    """Encrypt + upload the latest local snapshots to Cloudflare R2.

    soft=True (after a snapshot): missing config/passphrase is a silent skip.
    soft=False (explicit `offsite` command): report loudly and return non-zero
    so a misconfiguration is visible.
    """
    from bizclinik_erp.services import offsite

    cfg = offsite.r2_config_from_env()
    passphrase = os.environ.get("BIZCLINIK_BACKUP_PASSPHRASE", "")
    if cfg is None:
        print("  Offsite (R2) not configured — set R2_ACCOUNT_ID, R2_BUCKET, "
              "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.")
        return 0 if soft else 2
    if not passphrase:
        print("  BIZCLINIK_BACKUP_PASSPHRASE not set — refusing unencrypted "
              "offsite upload.")
        return 0 if soft else 2
    try:
        results = offsite.push_snapshots(
            local_root=_dest_dir(), passphrase=passphrase, cfg=cfg)
    except Exception as exc:  # boto3 missing, auth failure, network, etc.
        print(f"  Offsite upload failed: {exc}")
        return 0 if soft else 1
    ok = [r for r in results if "error" not in r]
    for r in results:
        if "error" in r:
            print(f"  [offsite {r['scope']}] ERROR: {r['error']}")
        else:
            print(f"  [offsite {r['scope']}] s3://{cfg.bucket}/{r['key']}  "
                  f"({r['bytes']} bytes"
                  + (f", pruned {r['pruned']}" if r.get('pruned') else "") + ")")
    print(f"Pushed {len(ok)} encrypted snapshot(s) to R2 bucket '{cfg.bucket}'.")
    return 0


def cmd_offsite(_args: argparse.Namespace) -> int:
    return _offsite_push(soft=False)


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
        description="Snapshot / list / restore Trakit365 ERP sqlite database.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="Take a new snapshot, prune, and push to R2 if configured.")
    p_snap.add_argument("--no-offsite", action="store_true",
                        help="Skip the Cloudflare R2 upload even if configured.")
    sub.add_parser("list", help="List existing snapshots.")
    sub.add_parser("offsite", help="Encrypt + push the latest local snapshots to Cloudflare R2.")

    p_restore = sub.add_parser("restore", help="Restore a snapshot over the live DB.")
    p_restore.add_argument("path", help="Path to snapshot file (absolute or relative to backups/).")

    return p


HANDLERS = {
    "snapshot": cmd_snapshot,
    "list": cmd_list,
    "offsite": cmd_offsite,
    "restore": cmd_restore,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
