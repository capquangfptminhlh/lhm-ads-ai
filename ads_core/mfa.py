"""Optional TOTP multi-factor authentication (RFC 6238) for browser accounts.

Secrets are generated locally, stored AES-GCM-sealed under the credential-vault
key, and never sent anywhere. Standard authenticator apps (Google/Microsoft
Authenticator, Authy, 1Password…) work via the otpauth:// URI. Enabling MFA is
per user and opt-in; once enabled, /api/login refuses a session until a valid
6-digit code is supplied with the password.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .app import app, require
from .db import audit, connection
from .security import seal, unseal, verify_password

ISSUER = 'LHM Ads AI'
STEP = 30
DIGITS = 6


def _init(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS user_mfa (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        secret_ciphertext TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    );
    ''')


def _b32(raw: bytes) -> str:
    return base64.b32encode(raw).decode('ascii').rstrip('=')


def _hotp(secret_b32: str, counter: int) -> str:
    padding = '=' * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + padding)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(code).zfill(DIGITS)


def totp(secret_b32: str, now: int | None = None) -> str:
    return _hotp(secret_b32, int(time.time() if now is None else now) // STEP)


def verify_totp(secret_b32: str, code: str, now: int | None = None) -> bool:
    if not isinstance(code, str):
        return False
    code = code.strip().replace(' ', '')
    if len(code) != DIGITS or not code.isdigit():
        return False
    current = int(time.time() if now is None else now) // STEP
    return any(hmac.compare_digest(_hotp(secret_b32, current + drift), code)
               for drift in (0, -1, 1))


def _row(db, user_id: int):
    _init(db)
    return db.execute('SELECT secret_ciphertext, enabled FROM user_mfa WHERE user_id=?',
                      (user_id,)).fetchone()


def _secret_of(row, user_id: int) -> str:
    return unseal(row['secret_ciphertext'], f'mfa:{user_id}')


def mfa_enabled(user_id: int) -> bool:
    with connection() as db:
        row = _row(db, user_id)
        return bool(row and row['enabled'])


def verify_user_totp(user_id: int, code: str | None) -> bool:
    if not code:
        return False
    with connection() as db:
        row = _row(db, user_id)
        if not row or not row['enabled']:
            return False
        return verify_totp(_secret_of(row, user_id), code)


def otpauth_uri(secret_b32: str, email: str) -> str:
    label = quote(f'{ISSUER}:{email}', safe='')
    return (f'otpauth://totp/{label}?secret={secret_b32}'
            f'&issuer={quote(ISSUER, safe="")}&digits={DIGITS}&period={STEP}')


@app.get('/api/me/mfa')
def mfa_status(ident=Depends(require('admin', 'operator', 'reader'))):
    with connection() as db:
        row = _row(db, ident['id'])
    return {'enabled': bool(row and row['enabled']),
            'pending_setup': bool(row and not row['enabled'])}


@app.post('/api/me/mfa/setup')
def mfa_setup(ident=Depends(require('admin', 'operator', 'reader'))):
    """Start (or restart) enrolment; MFA only activates after a valid code."""
    secret = _b32(secrets.token_bytes(20))
    with connection() as db:
        _init(db)
        row = _row(db, ident['id'])
        if row and row['enabled']:
            raise HTTPException(409, 'MFA đang bật; hãy tắt trước khi tạo khóa mới')
        db.execute('''INSERT INTO user_mfa(user_id, secret_ciphertext, enabled, created_at)
                      VALUES(?,?,0,?) ON CONFLICT(user_id) DO UPDATE SET
                      secret_ciphertext=excluded.secret_ciphertext, enabled=0,
                      created_at=excluded.created_at''',
                   (ident['id'], seal(secret, f"mfa:{ident['id']}"), int(time.time())))
        audit(db, ident, 'auth.mfa_setup', 'TOTP enrolment started (not yet enabled)')
    return {'secret': secret, 'otpauth_uri': otpauth_uri(secret, ident['email']),
            'message': 'Quét mã bằng ứng dụng xác thực rồi nhập mã 6 số để bật MFA. '
                       'Khóa chỉ hiện lần này trong phiên thiết lập.'}


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@app.post('/api/me/mfa/enable')
def mfa_enable(body: MfaCode, ident=Depends(require('admin', 'operator', 'reader'))):
    from .security import (
        MFA_MAX_ATTEMPTS, attempt_blocked, attempt_failed, attempt_succeeded,
        mfa_scope,
    )
    scope = mfa_scope(ident['id'], 'enable')
    with connection() as db:
        if attempt_blocked(db, scope, MFA_MAX_ATTEMPTS):
            raise HTTPException(429, 'Đã thử quá nhiều lần. Vui lòng đợi 15 phút rồi thử lại.')
        row = _row(db, ident['id'])
        if not row:
            raise HTTPException(409, 'Chưa bắt đầu thiết lập MFA')
        if row['enabled']:
            raise HTTPException(409, 'MFA đã được bật')
        if not verify_totp(_secret_of(row, ident['id']), body.code):
            attempt_failed(db, scope)
            raise HTTPException(403, 'Mã xác thực không đúng')
        attempt_succeeded(db, scope)
        db.execute('UPDATE user_mfa SET enabled=1 WHERE user_id=?', (ident['id'],))
        audit(db, ident, 'auth.mfa_enabled', 'TOTP MFA enabled for this account')
    return {'ok': True, 'message': 'Đã bật MFA. Từ lần đăng nhập sau, hệ thống sẽ yêu cầu mã 6 số.'}


class MfaDisable(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=8)


@app.post('/api/me/mfa/disable')
def mfa_disable(body: MfaDisable, ident=Depends(require('admin', 'operator', 'reader'))):
    from .security import (
        MFA_MAX_ATTEMPTS, attempt_blocked, attempt_failed, attempt_succeeded,
        mfa_scope,
    )
    scope = mfa_scope(ident['id'], 'disable')
    with connection() as db:
        if attempt_blocked(db, scope, MFA_MAX_ATTEMPTS):
            raise HTTPException(429, 'Đã thử quá nhiều lần. Vui lòng đợi 15 phút rồi thử lại.')
        user = db.execute('SELECT password_hash FROM users WHERE id=?',
                          (ident['id'],)).fetchone()
        row = _row(db, ident['id'])
        if not row or not row['enabled']:
            raise HTTPException(409, 'MFA chưa được bật')
        if not user or not verify_password(user['password_hash'], body.password):
            attempt_failed(db, scope)
            raise HTTPException(403, 'Mật khẩu hiện tại không đúng')
        if not verify_totp(_secret_of(row, ident['id']), body.code):
            attempt_failed(db, scope)
            raise HTTPException(403, 'Mã xác thực không đúng')
        attempt_succeeded(db, scope)
        db.execute('DELETE FROM user_mfa WHERE user_id=?', (ident['id'],))
        audit(db, ident, 'auth.mfa_disabled', 'TOTP MFA disabled after password + code check')
    return {'ok': True, 'message': 'Đã tắt MFA cho tài khoản này.'}
