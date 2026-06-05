"""Encrypted offsite backup: crypto round-trip + R2 push/prune (fake client)."""
from __future__ import annotations

from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# Encryption                                                                   #
# --------------------------------------------------------------------------- #

def test_encrypt_decrypt_round_trip():
    from bizclinik_erp.services import offsite
    data = b"SQLite format 3\x00" + b"the books" * 1000
    blob = offsite.encrypt_bytes(data, "correct horse battery staple")
    assert blob.startswith(offsite.MAGIC)
    assert blob != data
    assert offsite.decrypt_bytes(blob, "correct horse battery staple") == data


def test_wrong_passphrase_fails():
    from bizclinik_erp.services import offsite
    blob = offsite.encrypt_bytes(b"secret books", "right-pass")
    with pytest.raises(Exception):
        offsite.decrypt_bytes(blob, "wrong-pass")


def test_empty_passphrase_rejected():
    from bizclinik_erp.services import offsite
    with pytest.raises(ValueError):
        offsite.encrypt_bytes(b"x", "")


def test_file_round_trip(tmp_path):
    from bizclinik_erp.services import offsite
    src = tmp_path / "db.sqlite"
    src.write_bytes(b"\x00\x01\x02payload")
    enc = offsite.encrypt_file(src, tmp_path / "db.enc", "pw")
    dec = offsite.decrypt_file(enc, tmp_path / "db.out", "pw")
    assert dec.read_bytes() == src.read_bytes()


def test_corrupted_blob_detected():
    from bizclinik_erp.services import offsite
    with pytest.raises(ValueError):
        offsite.decrypt_bytes(b"not-an-encrypted-backup", "pw")


# --------------------------------------------------------------------------- #
# Config                                                                       #
# --------------------------------------------------------------------------- #

def test_config_from_env_derives_endpoint(monkeypatch):
    from bizclinik_erp.services import offsite
    for k in ("R2_ENDPOINT",):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("R2_BUCKET", "bizclinik-backups")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk")
    cfg = offsite.r2_config_from_env()
    assert cfg is not None
    assert cfg.endpoint == "https://abc123.r2.cloudflarestorage.com"
    assert cfg.bucket == "bizclinik-backups"


def test_config_none_when_incomplete(monkeypatch):
    from bizclinik_erp.services import offsite
    for k in ("R2_ACCOUNT_ID", "R2_ENDPOINT", "R2_BUCKET",
              "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("R2_BUCKET", "only-bucket")
    assert offsite.r2_config_from_env() is None


# --------------------------------------------------------------------------- #
# Push + prune with an in-memory fake S3 client                                #
# --------------------------------------------------------------------------- #

class FakeS3:
    def __init__(self):
        self.objs: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objs[(Bucket, Key)] = Body

    def list_objects_v2(self, Bucket, Prefix):
        keys = [{"Key": k} for (b, k) in self.objs if b == Bucket and k.startswith(Prefix)]
        return {"Contents": keys} if keys else {}

    def delete_object(self, Bucket, Key):
        self.objs.pop((Bucket, Key), None)


def _make_local_snapshots(root: Path):
    """Mimic backup.snapshot_all output: per-scope folders of bizclinik_*.db."""
    for scope, stamps in {
        "default": ["20260601-000000", "20260602-000000"],
        "control": ["20260602-000000"],
        "tenant-wendysrack": ["20260602-000000"],
    }.items():
        d = root / scope
        d.mkdir(parents=True)
        for ts in stamps:
            (d / f"bizclinik_{ts}.db").write_bytes(f"{scope}:{ts}".encode())


def test_push_uploads_newest_per_scope_encrypted(tmp_path):
    from bizclinik_erp.services import offsite
    root = tmp_path / "backups"
    _make_local_snapshots(root)
    cfg = offsite.R2Config(endpoint="https://x.r2.cloudflarestorage.com",
                           access_key_id="ak", secret_access_key="sk",
                           bucket="buk", prefix="bizclinik")
    client = FakeS3()
    results = offsite.push_snapshots(local_root=root, passphrase="pw",
                                     cfg=cfg, client=client)
    scopes = {r["scope"] for r in results if "error" not in r}
    assert scopes == {"default", "control", "tenant-wendysrack"}

    # Newest 'default' snapshot uploaded (20260602), under the right key.
    key = "bizclinik/default/bizclinik_20260602-000000.db.enc"
    assert ("buk", key) in client.objs
    # Stored object is encrypted (magic header), not plaintext.
    blob = client.objs[("buk", key)]
    assert blob.startswith(offsite.MAGIC)
    assert offsite.decrypt_bytes(blob, "pw") == b"default:20260602-000000"


def test_push_refuses_without_passphrase(tmp_path):
    from bizclinik_erp.services import offsite
    root = tmp_path / "backups"
    _make_local_snapshots(root)
    cfg = offsite.R2Config(endpoint="https://x", access_key_id="ak",
                           secret_access_key="sk", bucket="buk")
    with pytest.raises(ValueError):
        offsite.push_snapshots(local_root=root, passphrase="", cfg=cfg,
                               client=FakeS3())


def test_remote_prune_keeps_newest_n(tmp_path):
    from bizclinik_erp.services import offsite
    cfg = offsite.R2Config(endpoint="https://x", access_key_id="ak",
                           secret_access_key="sk", bucket="buk", prefix="bizclinik")
    client = FakeS3()
    # Seed 5 remote objects for one scope.
    for ts in ["20260601", "20260602", "20260603", "20260604", "20260605"]:
        client.objs[("buk", f"bizclinik/default/bizclinik_{ts}-000000.db.enc")] = b"x"
    pruned = offsite._prune_remote(client, cfg, "default", retain=2)
    assert len(pruned) == 3
    remaining = offsite._remote_keys(client, cfg, "default")
    assert remaining == [
        "bizclinik/default/bizclinik_20260604-000000.db.enc",
        "bizclinik/default/bizclinik_20260605-000000.db.enc",
    ]
