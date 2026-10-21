"""Portable, password-encrypted customer backup; never export raw Ads tokens.

The backup contains a consistent SQLite snapshot and the matching AES-GCM
MASTER_KEY encrypted using a user-supplied passphrase. The Windows DPAPI
settings file, sessions, and device-bound license are never copied into it.
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
MAX_DATABASE_BYTES = 64 * 1024 * 1024
SALT_BYTES = 16
NONCE_BYTES = 12
KDF_N = 1 << 15


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


def decrypt_snapshot(contents: bytes, passphrase: str) -> tuple[bytes, bytes]:
    min_bytes = len(MAGIC) + SALT_BYTES + NONCE_BYTES + 32 + 16
    if not isinstance(contents, bytes) or not min_bytes <= len(contents) <= MAX_DATABASE_BYTES + 2048:
        raise ValueError('File sao lưu không hợp lệ hoặc quá dung lượng')
    if not contents.startswith(MAGIC):
        raise ValueError('Không đúng định dạng LHM Ads AI Backup')
    offset = len(MAGIC)
    salt = contents[offset:offset + SALT_BYTES]
    nonce = contents[offset + SALT_BYTES:offset + SALT_BYTES + NONCE_BYTES]
    header = contents[:offset + SALT_BYTES + NONCE_BYTES]
    try:
        data = AESGCM(_key(passphrase, salt)).decrypt(nonce, contents[len(header):], header)
    except (InvalidTag, ValueError):
        raise ValueError('Sai mật khẩu hoặc file sao lưu bị sửa đổi') from None
    key, database = data[:32], data[32:]
    if len(key) != 32 or not database.startswith(b'SQLite format 3\x00'):
        raise ValueError('Dữ liệu trong bản sao lưu không hợp lệ')
    # Check the restored image before we ever place it on disk.
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
    return key, database


def restore_into_empty_directory(contents: bytes, passphrase: str, destination: Path):
    """Offline support-only restore; never overwrite an existing installation.

    The new Windows user gets a fresh DPAPI envelope and SESSION_SECRET.
    Machine-bound licenses, local monitor flags and install identifiers are
    not transferred; merchant must reissue the license on the new machine.
    """
    destination = Path(destination).expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError('Thư mục khôi phục phải trống; không ghi đè dữ liệu khách hàng')
    key, database = decrypt_snapshot(contents, passphrase)
    from .windows_vault import _save_settings
    destination.mkdir(parents=True, exist_ok=True)
    data_dir = destination / 'data'
    data_dir.mkdir(exist_ok=True)
    backup_file = data_dir / 'lhm-ads.sqlite3'
    handle = os.open(backup_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(handle, 'wb') as output:
            output.write(database)
            output.flush()
            os.fsync(output.fileno())
        _save_settings(destination / 'local-settings.json', {
            'MASTER_KEY': base64.b64encode(key).decode('ascii'),
            'SESSION_SECRET': secrets.token_urlsafe(48)})
    except Exception:
        backup_file.unlink(missing_ok=True)
        (destination / 'local-settings.json').unlink(missing_ok=True)
        raise
    return {'restored': True, 'license_transferred': False,
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
        backup = encrypt_snapshot(snapshot, master_key(), body.passphrase)
    except (ValueError, OSError, sqlite3.DatabaseError):
        raise HTTPException(422, 'Không thể tạo sao lưu mã hóa. Kiểm tra dung lượng dữ liệu và thử lại.') from None
    return Response(
        backup, media_type='application/octet-stream',
        headers={'Content-Disposition': 'attachment; filename="lhm-ads-backup.lhmbak"',
                 'Cache-Control': 'no-store',
                 'X-Content-Type-Options': 'nosniff'})
