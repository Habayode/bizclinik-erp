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
    code = 0
    if not getattr(_args, "no_offsite", False):
        code = _offsite_push(soft=True)  # non-zero if a CONFIGURED offsite is broken
    return code


def _offsite_push(*, soft: bool) -> int:
    """Encrypt + upload the latest local snapshots to Cloudflare R2.

    If R2 is NOT configured at all, offsite is genuinely off and we skip (a
    valid local-only mode): returns 0 for the nightly run, 2 for an explicit
    `offsite` command. If R2 IS configured, offsite is INTENDED, so a missing
    passphrase or any upload failure is a real misconfiguration and fails LOUDLY
    (non-zero) even on the nightly run — we must never silently end up with no
    offsite copy of the books.
    """
    from bizclinik_erp.services import offsite

    cfg = offsite.r2_config_from_env()
    passphrase = os.environ.get("BIZCLINIK_BACKUP_PASSPHRASE", "")
    if cfg is None:
        print("  Offsite (R2) not configured — local snapshot only (set "
              "R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY).")
        return 0 if soft else 2
    if not passphrase:
        print("  ERROR: R2 is configured but BIZCLINIK_BACKUP_PASSPHRASE is not "
              "set — offsite backup is BROKEN (refusing unencrypted upload).")
        return 2
    try:
        results = offsite.push_snapshots(
            local_root=_dest_dir(), passphrase=passphrase, cfg=cfg)
    except Exception as exc:  # boto3 missing, auth failure, network, etc.
        print(f"  ERROR: offsite upload failed: {exc}")
        return 1
    errs = [r for r in results if "error" in r]
    for r in results:
        if "error" in r:
            print(f"  [offsite {r['scope']}] ERROR: {r['error']}")
        else:
            print(f"  [offsite {r['scope']}] s3://{cfg.bucket}/{r['key']}  "
                  f"({r['bytes']} bytes"
                  + (f", pruned {r['pruned']}" if r.get('pruned') else "") + ")")
    if errs:
        print(f"  ERROR: {len(errs)} offsite scope(s) FAILED — offsite copy incomplete.")
        return 1
    print(f"Pushed {len(results)} encrypted snapshot(s) to R2 bucket '{cfg.bucket}'.")
    return 0


def cmd_verify(_args: argparse.Namespace) -> int:
    """Restore-drill: download the newest offsite backup for each scope, decrypt
    it with the configured passphrase, and confirm it is restorable. Fails loudly
    if any latest offsite copy can't be decrypted/recognised."""
    from bizclinik_erp.services import offsite

    cfg = offsite.r2_config_from_env()
    passphrase = os.environ.get("BIZCLINIK_BACKUP_PASSPHRASE", "")
    if cfg is None:
        print("Offsite (R2) not configured — nothing to verify.")
        return 0
    if not passphrase:
        print("ERROR: BIZCLINIK_BACKUP_PASSPHRASE not set — cannot verify offsite.")
        return 2
    try:
        results = offsite.verify_latest(cfg=cfg, passphrase=passphrase)
    except Exception as exc:
        print(f"ERROR: offsite verify failed: {exc}")
        return 1
    if not results:
        print("ERROR: no offsite snapshots found to verify.")
        return 1
    bad = [r for r in results if not r.get("ok")]
    for r in results:
        status = "OK  " if r.get("ok") else "FAIL"
        print(f"  [{status}] {r['scope']}: {r.get('key', '')} "
              f"({r.get('bytes', 0)} bytes)"
              + (f" — {r['detail']}" if r.get("detail") else ""))
    if bad:
        print(f"ERROR: {len(bad)} offsite backup(s) NOT restorable.")
        return 1
    print(f"All {len(results)} latest offsite backup(s) decrypt and look restorable.")
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
    sub.add_parser("verify", help="Restore-drill: download + decrypt the latest offsite backups and confirm they are restorable.")

    p_restore = sub.add_parser("restore", help="Restore a snapshot over the live DB.")
    p_restore.add_argument("path", help="Path to snapshot file (absolute or relative to backups/).")

    return p


HANDLERS = {
    "snapshot": cmd_snapshot,
    "list": cmd_list,
    "offsite": cmd_offsite,
    "verify": cmd_verify,
    "restore": cmd_restore,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
