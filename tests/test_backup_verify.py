"""Offsite backup integrity: encrypt -> round-trip verify -> upload, and the
restore-drill (verify_latest) that downloads + decrypts the newest object and
confirms it is a restorable backup. Uses an in-memory fake S3 client — no R2."""
from __future__ import annotations

import io

from bizclinik_erp.services import offsite


class FakeS3:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body, **kw):
        self.store[Key] = Body

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in sorted(self.store) if k.startswith(Prefix)]}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.store[Key])}

    def delete_object(self, Bucket, Key):
        self.store.pop(Key, None)


def _cfg():
    return offsite.R2Config(endpoint="https://x", access_key_id="a",
                            secret_access_key="b", bucket="bk", prefix="bizclinik")


def test_looks_like_backup():
    assert offsite._looks_like_backup(b"SQLite format 3\x00....")
    assert offsite._looks_like_backup(b"--\n-- PostgreSQL database dump\n--\nSET x;")
    assert offsite._looks_like_backup(b"PGDMP\x01\x14")
    assert not offsite._looks_like_backup(b"this is random garbage not a backup")


def test_push_roundtrip_and_verify(tmp_path):
    root = tmp_path / "backups"
    (root / "control").mkdir(parents=True)
    snap = root / "control" / "bizclinik_20260101-000000.sql"
    snap.write_bytes(b"--\n-- PostgreSQL database dump\n--\nSET statement_timeout = 0;\n")
    fake = FakeS3()
    res = offsite.push_snapshots(local_root=root, passphrase="pw", cfg=_cfg(), client=fake)
    assert res and "error" not in res[0]
    assert any(k.endswith(".sql.enc") for k in fake.store)
    # Correct passphrase -> the latest offsite copy decrypts and is restorable.
    v = offsite.verify_latest(cfg=_cfg(), passphrase="pw", client=fake)
    assert v and v[0]["scope"] == "control" and v[0]["ok"] is True
    # Wrong passphrase -> decrypt fails -> not restorable.
    v2 = offsite.verify_latest(cfg=_cfg(), passphrase="WRONG", client=fake)
    assert v2 and v2[0]["ok"] is False


def test_verify_rejects_unrecognised_content(tmp_path):
    fake = FakeS3()
    fake.store["bizclinik/control/bizclinik_x.sql.enc"] = offsite.encrypt_bytes(
        b"decrypts fine but is not a database backup", "pw")
    v = offsite.verify_latest(cfg=_cfg(), passphrase="pw", client=fake)
    assert v and v[0]["ok"] is False
