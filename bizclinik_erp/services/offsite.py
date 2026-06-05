"""Encrypted offsite backup to Cloudflare R2 (S3-compatible object storage).

Local snapshots (services.backup.snapshot_all) live on the same droplet as the
database — if the droplet dies, so do the books. This module pushes those
snapshots to Cloudflare R2 so there is always an off-box copy.

Defence in depth:
  • Client-side encryption — each snapshot is encrypted with a passphrase
    (BIZCLINIK_BACKUP_PASSPHRASE) BEFORE it leaves the box, so the object in R2
    is unreadable even to the storage provider. Format:
        MAGIC || 16-byte salt || Fernet(token)
    where the Fernet key is PBKDF2-HMAC-SHA256(passphrase, salt, 200k iters).
  • Per-scope retention — keeps the newest N encrypted snapshots per scope.

R2 is configured from the environment (see r2_config_from_env). boto3 is only
imported when an upload actually happens, so this module imports fine without it
(and the pure crypto functions stay unit-testable on any box).
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


MAGIC = b"BZKENC1\n"
SALT_LEN = 16
KDF_ITERS = 200_000
DEFAULT_PREFIX = "bizclinik"
DEFAULT_RETAIN = 14


# --------------------------------------------------------------------------- #
# Client-side encryption                                                       #
# --------------------------------------------------------------------------- #

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not passphrase:
        raise ValueError("A non-empty backup passphrase is required.")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=KDF_ITERS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_bytes(data: bytes, passphrase: str) -> bytes:
    """Return MAGIC || salt || Fernet token for ``data``."""
    salt = os.urandom(SALT_LEN)
    token = Fernet(_derive_key(passphrase, salt)).encrypt(data)
    return MAGIC + salt + token


def decrypt_bytes(blob: bytes, passphrase: str) -> bytes:
    """Inverse of :func:`encrypt_bytes`. Raises on tampering / wrong passphrase."""
    if not blob.startswith(MAGIC):
        raise ValueError("Not a BizClinik encrypted backup (bad magic header).")
    body = blob[len(MAGIC):]
    salt, token = body[:SALT_LEN], body[SALT_LEN:]
    return Fernet(_derive_key(passphrase, salt)).decrypt(token)


def encrypt_file(src: Path, dest: Path, passphrase: str) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(encrypt_bytes(Path(src).read_bytes(), passphrase))
    return dest


def decrypt_file(src: Path, dest: Path, passphrase: str) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(decrypt_bytes(Path(src).read_bytes(), passphrase))
    return dest


# --------------------------------------------------------------------------- #
# R2 configuration + client                                                    #
# --------------------------------------------------------------------------- #

@dataclass
class R2Config:
    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    prefix: str = DEFAULT_PREFIX


def r2_config_from_env() -> Optional[R2Config]:
    """Build an R2Config from the environment, or None if not fully configured.

    Reads R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET and either
    R2_ENDPOINT or R2_ACCOUNT_ID (endpoint derived as
    https://<account>.r2.cloudflarestorage.com). R2_PREFIX is optional.
    """
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    bucket = os.environ.get("R2_BUCKET")
    endpoint = os.environ.get("R2_ENDPOINT")
    account = os.environ.get("R2_ACCOUNT_ID")
    if not endpoint and account:
        endpoint = f"https://{account}.r2.cloudflarestorage.com"
    if not (ak and sk and bucket and endpoint):
        return None
    return R2Config(endpoint=endpoint, access_key_id=ak, secret_access_key=sk,
                    bucket=bucket, prefix=os.environ.get("R2_PREFIX", DEFAULT_PREFIX))


def make_client(cfg: R2Config):
    """Construct a boto3 S3 client pointed at R2. Imports boto3 lazily."""
    import boto3  # noqa: PLC0415 -- optional dependency, only needed to upload
    from botocore.config import Config as _BotoConfig
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key_id,
        aws_secret_access_key=cfg.secret_access_key,
        region_name="auto",
        config=_BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
    )


# --------------------------------------------------------------------------- #
# Push + prune                                                                 #
# --------------------------------------------------------------------------- #

def _remote_keys(client, cfg: R2Config, scope: str) -> list[str]:
    prefix = f"{cfg.prefix}/{scope}/"
    resp = client.list_objects_v2(Bucket=cfg.bucket, Prefix=prefix)
    return sorted(o["Key"] for o in resp.get("Contents", []))


def _prune_remote(client, cfg: R2Config, scope: str, retain: int) -> list[str]:
    keys = _remote_keys(client, cfg, scope)  # sorted oldest->newest (ts in name)
    doomed = keys[:-retain] if retain > 0 else []
    for k in doomed:
        client.delete_object(Bucket=cfg.bucket, Key=k)
    return doomed


def push_snapshots(
    *,
    local_root: Path,
    passphrase: str,
    cfg: R2Config,
    client=None,
    retain: int = DEFAULT_RETAIN,
) -> list[dict]:
    """Encrypt + upload the newest snapshot in each per-scope folder under
    ``local_root`` to R2, then prune remote copies to the newest ``retain``.

    ``local_root`` is the directory produced by backup.snapshot_all — one
    subfolder per scope (default/control/tenant-*), each holding bizclinik_*.db
    snapshots. Returns one result dict per scope.
    """
    from .backup import list_snapshots

    if not passphrase:
        raise ValueError(
            "BIZCLINIK_BACKUP_PASSPHRASE is not set — refusing to upload "
            "unencrypted books offsite.")
    client = client or make_client(cfg)
    local_root = Path(local_root)

    results: list[dict] = []
    if not local_root.exists():
        return results
    for scope_dir in sorted(p for p in local_root.iterdir() if p.is_dir()):
        snaps = list_snapshots(scope_dir)
        if not snaps:
            continue
        newest = snaps[-1]
        try:
            blob = encrypt_bytes(newest.read_bytes(), passphrase)
            key = f"{cfg.prefix}/{scope_dir.name}/{newest.name}.enc"
            client.put_object(Bucket=cfg.bucket, Key=key, Body=blob,
                              ContentType="application/octet-stream")
            pruned = _prune_remote(client, cfg, scope_dir.name, retain)
            results.append({"scope": scope_dir.name, "key": key,
                            "bytes": len(blob), "pruned": len(pruned)})
        except Exception as exc:  # pragma: no cover - defensive per-scope
            results.append({"scope": scope_dir.name, "error": str(exc)})
    return results
