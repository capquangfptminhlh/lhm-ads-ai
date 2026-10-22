"""Portable, password-encrypted customer backup; never export raw Ads tokens.

The backup contains a consistent SQLite snapshot and the matching AES-GCM
MASTER_KEY encrypted using a user-supplied passphrase. The Windows DPAPI
settings file, sessions, and device-bound license are never copied into it.

Format V2 additionally carries the offline license-revocation list
(``revocations.json`` plus its detached ``.sig``) VERBATIM when one exists
on the source install. The license itself stays device-bound and is NOT
transferred, but the revocation list is seller-signed data about OTHER
licenses; if it were lost in a machine move, a license the seller already
revoked could be reissued and would verify as good on the new machine
because the new install has no list. Copying the bytes exactly (never
re-signing, never "repairing") keeps the loader's fail-closed signature
verification in ads_core.license_revocation fully in charge.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import sqlite3
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .app import app, browser_admin
from .db import DB_PATH
from .desktop_onboarding import desktop_only
from .security import master_key

MAGIC = b'LHM-ADS-BACKUP-V1\n'
MAGIC_V2 = b'LHM-ADS-BACKUP-V2\n'
MAX_DATABASE_BYTES = 64 * 1024 * 1024
SALT_BYTES = 16
NONCE_BYTES = 12
KDF_N = 1 << 15
# Revocation payload caps, mirroring ads_core.license_revocation limits
# (list <= 256 KiB; the .sig is base64 of 64 bytes, so 4 KiB is generous).
MAX_REVOCATION_BYTES = 256 * 1024
MAX_REVOCATION_SIG_BYTES = 4096
# V2 containers may exceed the V1 size cap by the revocation payload.
MAX_BACKUP_V2_BYTES = MAX_DATABASE_BYTES + MAX_REVOCATION_BYTES + MAX_REVOCATION_SIG_BYTES + 4096


def _key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 16 or len(passphrase) > 256:
        raise ValueError('Mật khẩu sao lưu phải từ 16 đến 256 ký tự')
    if len(salt) != SALT_BYTES:
        raise ValueError('Invalid salt')
    return Scrypt(salt=salt, length=32, n=KDF_N, r=8, p=1).derive(
        passphrase.encode('utf-8'))


def sqlite_snapshot(path: Path) -> bytes:
    """Online consistent snapshot, never copying WAL/shm or an inconsistent db."""
    path = Path(path)
    if not path.is_file():
        raise ValueError('Chưa có dữ liệu để sao lưu')
    if path.stat().st_size > MAX_DATABASE_BYTES:
        raise ValueError('Dữ liệu quá 64 MB; cần quy trình hỗ trợ sao lưu dung lượng lớn')
    source = sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro', uri=True, timeout=10)
    target = sqlite3.connect(':memory:')
    try:
        source.backup(target, pages=200, sleep=0.01)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Dữ liệu SQLite không toàn vẹn')
        # Logging in again after restore is mandatory; no active browser sessions.
        target.execute('DELETE FROM sessions')
        target.commit()
        # sqlite3.backup() copies the source WAL header flags even though
        # the in-memory snapshot has no accompanying -wal file. A restored
        # standalone database must use rollback journal mode instead.
        content = bytearray(target.serialize())
        if content[18:20] == b'\x02\x02':
            content[18:20] = b'\x01\x01'
        if content[18:20] != b'\x01\x01':
            raise ValueError('SQLite journal header không hợp lệ')
        if len(content) > MAX_DATABASE_BYTES:
            raise ValueError('Dữ liệu quá 64 MB')
        return bytes(content)
    finally:
        target.close()
        source.close()


def encrypt_snapshot(database: bytes, key: bytes, passphrase: str,
                     *, salt: bytes | None = None, nonce: bytes | None = None) -> bytes:
    if len(key) != 32 or not database.startswith(b'SQLite format 3\x00'):
        raise ValueError('Invalid encrypted backup inputs')
    if len(database) > MAX_DATABASE_BYTES:
        raise ValueError('Snapshot too large')
    salt = secrets.token_bytes(SALT_BYTES) if salt is None else salt
    nonce = secrets.token_bytes(NONCE_BYTES) if nonce is None else nonce
    if len(nonce) != NONCE_BYTES:
        raise ValueError('Invalid nonce')
    header = MAGIC + salt + nonce
    sealed = AESGCM(_key(passphrase, salt)).encrypt(
        nonce, key + database, header)
    return header + sealed


def _check_database_image(database: bytes) -> None:
    """Check the restored image before we ever place it on disk."""
    if not database.startswith(b'SQLite format 3\x00'):
        raise ValueError('Dữ liệu trong bản sao lưu không hợp lệ')
    memory = sqlite3.connect(':memory:')
    try:
        memory.deserialize(database)
        if memory.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        if not {'users', 'accounts', 'sessions'}.issubset(
                {x[0] for x in memory.execute("SELECT name FROM sqlite_master WHERE type='table'")}):
            raise ValueError('File không phải database LHM Ads AI')
    except sqlite3.DatabaseError:
        raise ValueError('Dữ liệu sao lưu SQLite bị lỗi') from None
    finally:
        memory.close()


def _open_container(contents: bytes, passphrase: str, magic: bytes) -> bytes:
    """Decrypt one container (either format) and return its plaintext."""
    offset = len(magic)
    salt = contents[offset:offset + SALT_BYTES]
    nonce = contents[offset + SALT_BYTES:offset + SALT_BYTES + NONCE_BYTES]
    header = contents[:offset + SALT_BYTES + NONCE_BYTES]
    try:
        return AESGCM(_key(passphrase, salt)).decrypt(nonce, contents[len(header):], header)
    except (InvalidTag, ValueError):
        raise ValueError('Sai mật khẩu hoặc file sao lưu bị sửa đổi') from None


def _decode_extras(raw: bytes) -> tuple[bytes | None, bytes | None]:
    """Strictly decode the V2 extras block into (revocations, revocations_sig).

    The bytes are the customer's own revocation list, copied verbatim; this
    decoder checks only container-level shape/size/base64 sanity. Whether
    the list itself is trustworthy remains the job of
    ads_core.license_revocation at load time — a tampered list restores as
    tampered bytes and still fails closed there, never laundered here.
    """
    if not raw:
        return None, None
    try:
        extras = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('Dữ liệu phụ trong bản sao lưu không hợp lệ') from None
    if not isinstance(extras, dict) or not set(extras) <= {'revocations_b64', 'revocations_sig_b64'}:
        raise ValueError('Dữ liệu phụ trong bản sao lưu không hợp lệ')

    def _field(name, cap):
        value = extras.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('Dữ liệu phụ trong bản sao lưu không hợp lệ')
        try:
            decoded = base64.b64decode(value, validate=True)
        except ValueError:
            raise ValueError('Dữ liệu phụ trong bản sao lưu không hợp lệ') from None
        if not 1 <= len(decoded) <= cap:
            raise ValueError('Dữ liệu phụ trong bản sao lưu không hợp lệ')
        return decoded

    return (_field('revocations_b64', MAX_REVOCATION_BYTES),
            _field('revocations_sig_b64', MAX_REVOCATION_SIG_BYTES))


def decrypt_backup(contents: bytes, passphrase: str) -> dict:
    """Decrypt a V1 or V2 backup.

    Returns {'key', 'database', 'revocations', 'revocations_sig'}; the two
    revocation fields are raw file bytes or None when the backup carries no
    revocation list (always None for V1 backups written before this field
    existed).
    """
    if isinstance(contents, bytes) and contents.startswith(MAGIC_V2):
        min_bytes = len(MAGIC_V2) + SALT_BYTES + NONCE_BYTES + 32 + 8 + 16
        if not min_bytes <= len(contents) <= MAX_BACKUP_V2_BYTES:
            raise ValueError('File sao lưu không hợp lệ hoặc quá dung lượng')
        data = _open_container(contents, passphrase, MAGIC_V2)
        if len(data) < 40:
            raise ValueError('Dữ liệu trong bản sao lưu không hợp lệ')
        key = data[:32]
        (db_length,) = struct.unpack('>Q', data[32:40])
        database = data[40:40 + db_length]
        if len(database) != db_length:
            raise ValueError('Dữ liệu trong bản sao lưu không hợp lệ')
        _check_database_image(database)
        revocations, revocations_sig = _decode_extras(data[40 + db_length:])
        return {'key': key, 'database': database,
                'revocations': revocations, 'revocations_sig': revocations_sig}
    min_bytes = len(MAGIC) + SALT_BYTES + NONCE_BYTES + 32 + 16
    if not isinstance(contents, bytes) or not min_bytes <= len(contents) <= MAX_DATABASE_BYTES + 2048:
        raise ValueError('File sao lưu không hợp lệ hoặc quá dung lượng')
    if not contents.startswith(MAGIC):
        raise ValueError('Không đúng định dạng LHM Ads AI Backup')
    data = _open_container(contents, passphrase, MAGIC)
    key, database = data[:32], data[32:]
    if len(key) != 32:
        raise ValueError('Dữ liệu trong bản sao lưu không hợp lệ')
    _check_database_image(database)
    return {'key': key, 'database': database, 'revocations': None, 'revocations_sig': None}


def decrypt_snapshot(contents: bytes, passphrase: str) -> tuple[bytes, bytes]:
    """Backward-compatible (key, database) view of decrypt_backup."""
    opened = decrypt_backup(contents, passphrase)
    return opened['key'], opened['database']


def encrypt_backup(database: bytes, key: bytes, passphrase: str, *,
                   revocations: bytes | None = None,
                   revocations_sig: bytes | None = None,
                   salt: bytes | None = None, nonce: bytes | None = None) -> bytes:
    """V2 container: key + length-prefixed database + optional extras.

    ``revocations``/``revocations_sig`` are the raw bytes of the source
    install's revocation list and its detached signature file, or None when
    the install has none. They are embedded verbatim — see module docstring.
    """
    if len(key) != 32 or not database.startswith(b'SQLite format 3\x00'):
        raise ValueError('Invalid encrypted backup inputs')
    if len(database) > MAX_DATABASE_BYTES:
        raise ValueError('Snapshot too large')
    extras = {}
    if revocations is not None:
        if not 1 <= len(revocations) <= MAX_REVOCATION_BYTES:
            raise ValueError('Danh sách thu hồi quá lớn hoặc rỗng; không thể sao lưu')
        extras['revocations_b64'] = base64.b64encode(revocations).decode('ascii')
    if revocations_sig is not None:
        if not 1 <= len(revocations_sig) <= MAX_REVOCATION_SIG_BYTES:
            raise ValueError('Chữ ký danh sách thu hồi không hợp lệ; không thể sao lưu')
        extras['revocations_sig_b64'] = base64.b64encode(revocations_sig).decode('ascii')
    salt = secrets.token_bytes(SALT_BYTES) if salt is None else salt
    nonce = secrets.token_bytes(NONCE_BYTES) if nonce is None else nonce
    if len(salt) != SALT_BYTES or len(nonce) != NONCE_BYTES:
        raise ValueError('Invalid salt or nonce')
    header = MAGIC_V2 + salt + nonce
    payload = key + struct.pack('>Q', len(database)) + database
    if extras:
        payload += json.dumps(extras, separators=(',', ':')).encode('utf-8')
    sealed = AESGCM(_key(passphrase, salt)).encrypt(nonce, payload, header)
    return header + sealed


def current_revocation_files() -> tuple[bytes | None, bytes | None]:
    """Raw (revocations.json, revocations.json.sig) bytes of THIS install.

    The path mirrors ads_core.licensing: LHM_REVOCATION_FILE when set, else
    'revocations.json' in the licensing folder next to the database. A
    missing list file means "no revocations known" and returns (None, None)
    — the same semantics the loader uses; a missing .sig next to an existing
    list returns (bytes, None) so the pair is preserved exactly as found.
    """
    configured = os.environ.get('LHM_REVOCATION_FILE')
    if configured:
        list_path = Path(configured)
    else:
        list_path = Path(DB_PATH()).resolve().parent / 'licensing' / 'revocations.json'
    if not list_path.is_file():
        return None, None
    revocations = list_path.read_bytes()
    sig_path = Path(str(list_path) + '.sig')
    revocations_sig = sig_path.read_bytes() if sig_path.is_file() else None
    return revocations, revocations_sig


def _write_new_file(path: Path, content: bytes) -> None:
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, 'wb') as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def _restore_revocation_files(destination: Path, revocations: bytes | None,
                              revocations_sig: bytes | None) -> bool:
    """Place the backup's revocation list next to the (future) license.

    The restored database lands in destination/data/, so the licensing
    folder of the restored install is destination/data/licensing/ — the
    same folder ads_core.licensing.license_folder resolves once the app
    runs there, and where the merchant-reissued license.json will live.

    No-un-revoke rule: when the backup carries NO list (every V1 backup,
    and V2 backups from installs that had none), this function performs no
    filesystem operation on revocation paths at all — it never creates,
    overwrites, or deletes a revocations file. Restoring stale state must
    never silently un-revoke a license. When the backup DOES carry a list,
    the bytes are written exactly as captured; signature verification is
    left to ads_core.license_revocation at load time, unchanged.
    """
    if revocations is None:
        return False
    licensing_dir = destination / 'data' / 'licensing'
    licensing_dir.mkdir(exist_ok=True)
    _write_new_file(licensing_dir / 'revocations.json', revocations)
    if revocations_sig is not None:
        _write_new_file(licensing_dir / 'revocations.json.sig', revocations_sig)
    return True


def restore_into_empty_directory(contents: bytes, passphrase: str, destination: Path):
    """Offline support-only restore; never overwrite an existing installation.

    The new Windows user gets a fresh DPAPI envelope and SESSION_SECRET.
    Machine-bound licenses, local monitor flags and install identifiers are
    not transferred; merchant must reissue the license on the new machine.
    A revocation list captured in a V2 backup IS restored (see
    _restore_revocation_files); a backup without one leaves revocation
    state completely untouched.
    """
    destination = Path(destination).expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError('Thư mục khôi phục phải trống; không ghi đè dữ liệu khách hàng')
    opened = decrypt_backup(contents, passphrase)
    key, database = opened['key'], opened['database']
    from .windows_vault import _save_settings
    destination.mkdir(parents=True, exist_ok=True)
    data_dir = destination / 'data'
    data_dir.mkdir(exist_ok=True)
    backup_file = data_dir / 'lhm-ads.sqlite3'
    revocations_transferred = False
    try:
        _write_new_file(backup_file, database)
        _save_settings(destination / 'local-settings.json', {
            'MASTER_KEY': base64.b64encode(key).decode('ascii'),
            'SESSION_SECRET': secrets.token_urlsafe(48)})
        revocations_transferred = _restore_revocation_files(
            destination, opened['revocations'], opened['revocations_sig'])
    except Exception:
        backup_file.unlink(missing_ok=True)
        (destination / 'local-settings.json').unlink(missing_ok=True)
        licensing_dir = destination / 'data' / 'licensing'
        (licensing_dir / 'revocations.json').unlink(missing_ok=True)
        (licensing_dir / 'revocations.json.sig').unlink(missing_ok=True)
        try:
            licensing_dir.rmdir()
        except OSError:
            pass
        raise
    return {'restored': True, 'license_transferred': False,
            'revocations_transferred': revocations_transferred,
            'login_sessions_transferred': False, 'requires_restart': True}


class BackupRequest(BaseModel):
    passphrase: str = Field(min_length=16, max_length=256)


@app.post('/api/desktop/backup/export')
def export_encrypted_backup(body: BackupRequest, request: Request,
                            ident=Depends(browser_admin)):
    del ident
    desktop_only(request)
    try:
        snapshot = sqlite_snapshot(Path(DB_PATH()))
        revocations, revocations_sig = current_revocation_files()
        if revocations is not None:
            # V2 container so the revocation list survives the machine move;
            # installs without a list keep producing the original V1 format.
            backup = encrypt_backup(snapshot, master_key(), body.passphrase,
                                    revocations=revocations,
                                    revocations_sig=revocations_sig)
        else:
            backup = encrypt_snapshot(snapshot, master_key(), body.passphrase)
    except (ValueError, OSError, sqlite3.DatabaseError):
        raise HTTPException(422, 'Không thể tạo sao lưu mã hóa. Kiểm tra dung lượng dữ liệu và thử lại.') from None
    return Response(
        backup, media_type='application/octet-stream',
        headers={'Content-Disposition': 'attachment; filename="lhm-ads-backup.lhmbak"',
                 'Cache-Control': 'no-store',
                 'X-Content-Type-Options': 'nosniff'})
