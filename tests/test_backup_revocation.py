"""Backup/restore coverage of the offline license-revocation list.

Audit finding (2026-10-22): the V1 backup carried ONLY the MASTER_KEY and
the SQLite snapshot — revocations.json was not backed up at all, so a
machine move silently dropped every revocation the seller had delivered.
These tests pin the V2 behaviour:

- a backup captures revocations.json + its detached .sig verbatim;
- restore writes them next to where the reissued license will live
  (destination/data/licensing/);
- a backup WITHOUT a list performs no operation on revocation state —
  restoring stale state must never un-revoke a license;
- a tampered list still fails closed after restore: backup/restore copies
  bytes, it never re-validates or "repairs" them, so
  ads_core.license_revocation keeps the final say.
"""
import base64
import json
import sqlite3
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ads_core import license_revocation as revocation
from ads_core import secure_backup
from ads_core.licensing import canonical

PASSPHRASE = 'mat khau sao luu du dai 2026'
KEY = b'K' * 32
NOW = int(time.time())


_snapshot_counter = [0]


def _make_snapshot(tmp_path):
    _snapshot_counter[0] += 1
    db_file = tmp_path / f'source-{_snapshot_counter[0]}.sqlite3'
    with sqlite3.connect(db_file) as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE sessions (id INTEGER PRIMARY KEY)')
        db.commit()
    return secure_backup.sqlite_snapshot(db_file)


def _keypair():
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return key, base64.b64encode(raw).decode()


def _signed_list(key, entries):
    document = {'version': 1, 'issued_at': NOW, 'entries': entries}
    raw = canonical(document)
    sig_text = base64.b64encode(key.sign(raw)).decode()
    return raw, sig_text.encode()


def _entry(**kw):
    entry = {'reason': 'Hoàn tiền cho khách', 'revoked_at': NOW}
    entry.update(kw)
    return entry


def _install_revocation(tmp_path, monkeypatch, raw, sig_bytes):
    """Place a revocation list where a real install would keep it."""
    data_dir = tmp_path / 'data'
    (data_dir / 'licensing').mkdir(parents=True)
    monkeypatch.setenv('DB_PATH', str(data_dir / 'lhm-ads.sqlite3'))
    monkeypatch.delenv('LHM_REVOCATION_FILE', raising=False)
    list_path = data_dir / 'licensing' / 'revocations.json'
    list_path.write_bytes(raw)
    (data_dir / 'licensing' / 'revocations.json.sig').write_bytes(sig_bytes)
    return list_path


def test_backup_includes_revocations_when_present(tmp_path, monkeypatch):
    key, _pub = _keypair()
    raw, sig = _signed_list(key, [_entry(license_id='lic-123')])
    _install_revocation(tmp_path, monkeypatch, raw, sig)

    found_raw, found_sig = secure_backup.current_revocation_files()
    assert found_raw == raw and found_sig == sig

    blob = secure_backup.encrypt_backup(
        _make_snapshot(tmp_path), KEY, PASSPHRASE,
        revocations=found_raw, revocations_sig=found_sig)
    assert blob.startswith(secure_backup.MAGIC_V2)
    opened = secure_backup.decrypt_backup(blob, PASSPHRASE)
    assert opened['revocations'] == raw
    assert opened['revocations_sig'] == sig
    # The legacy (key, database) view still works on a V2 container.
    got_key, got_db = secure_backup.decrypt_snapshot(blob, PASSPHRASE)
    assert got_key == KEY and got_db.startswith(b'SQLite format 3\x00')
    with pytest.raises(ValueError):
        secure_backup.decrypt_backup(blob, 'sai mat khau nhung du dai')


def test_current_revocation_files_absent_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'data' / 'lhm-ads.sqlite3'))
    monkeypatch.delenv('LHM_REVOCATION_FILE', raising=False)
    assert secure_backup.current_revocation_files() == (None, None)


def test_restore_restores_revocations_next_to_license(tmp_path, monkeypatch):
    key, pub = _keypair()
    raw, sig = _signed_list(key, [_entry(license_id='lic-123')])
    _install_revocation(tmp_path, monkeypatch, raw, sig)
    found_raw, found_sig = secure_backup.current_revocation_files()
    blob = secure_backup.encrypt_backup(
        _make_snapshot(tmp_path), KEY, PASSPHRASE,
        revocations=found_raw, revocations_sig=found_sig)

    destination = tmp_path / 'restored'
    result = secure_backup.restore_into_empty_directory(blob, PASSPHRASE, destination)
    assert result['revocations_transferred'] is True

    restored_list = destination / 'data' / 'licensing' / 'revocations.json'
    restored_sig = destination / 'data' / 'licensing' / 'revocations.json.sig'
    assert restored_list.read_bytes() == raw
    assert restored_sig.read_bytes() == sig
    # The restored list is fully functional under the normal loader: the
    # revocation survived the machine move.
    parsed = revocation.load_revocation_list(restored_list, public_key_b64=pub)
    revoked, _ = revocation.is_revoked(parsed, {'license_id': 'lic-123', 'device': 'x' * 32})
    assert revoked is True


def test_restore_without_revocations_never_touches_revocation_state(tmp_path):
    licensing_dir = tmp_path / 'dest' / 'data' / 'licensing'
    licensing_dir.mkdir(parents=True)
    existing = licensing_dir / 'revocations.json'
    existing_bytes = b'{"version":1,"issued_at":1,"entries":[]}'
    existing.write_bytes(existing_bytes)

    # A backup with no list must not create, overwrite, or delete anything.
    assert secure_backup._restore_revocation_files(tmp_path / 'dest', None, None) is False
    assert existing.read_bytes() == existing_bytes
    assert not (licensing_dir / 'revocations.json.sig').exists()

    # End to end: an old V1 backup restores fine and fabricates no list.
    blob = secure_backup.encrypt_snapshot(_make_snapshot(tmp_path), KEY, PASSPHRASE)
    assert blob.startswith(secure_backup.MAGIC)
    destination = tmp_path / 'restored-v1'
    result = secure_backup.restore_into_empty_directory(blob, PASSPHRASE, destination)
    assert result['restored'] is True
    assert result['revocations_transferred'] is False
    assert not (destination / 'data' / 'licensing' / 'revocations.json').exists()


def test_tampered_revocation_still_fails_closed_after_restore(tmp_path):
    key, pub = _keypair()
    raw, sig = _signed_list(key, [_entry(license_id='lic-123')])
    # Attacker edits the restored-to-be bytes: a different license id than
    # the one the seller signed. Backup copies bytes verbatim on purpose.
    tampered = json.loads(raw)
    tampered['entries'][0]['license_id'] = 'lic-999'
    tampered_raw = canonical(tampered)

    blob = secure_backup.encrypt_backup(
        _make_snapshot(tmp_path), KEY, PASSPHRASE,
        revocations=tampered_raw, revocations_sig=sig)
    destination = tmp_path / 'restored'
    secure_backup.restore_into_empty_directory(blob, PASSPHRASE, destination)
    restored_list = destination / 'data' / 'licensing' / 'revocations.json'
    assert restored_list.read_bytes() == tampered_raw
    with pytest.raises(revocation.RevocationError):
        revocation.load_revocation_list(restored_list, public_key_b64=pub)

    # And a restored list whose signature file is lost also fails closed
    # (missing .sig next to an existing list is an error, not "no list").
    blob_no_sig = secure_backup.encrypt_backup(
        _make_snapshot(tmp_path), KEY, PASSPHRASE, revocations=raw)
    destination2 = tmp_path / 'restored-nosig'
    secure_backup.restore_into_empty_directory(blob_no_sig, PASSPHRASE, destination2)
    restored_no_sig = destination2 / 'data' / 'licensing' / 'revocations.json'
    assert restored_no_sig.read_bytes() == raw
    assert not (destination2 / 'data' / 'licensing' / 'revocations.json.sig').exists()
    with pytest.raises(revocation.RevocationError):
        revocation.load_revocation_list(restored_no_sig, public_key_b64=pub)
