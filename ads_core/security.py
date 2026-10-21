"""Argon2 passwords; AES-256-GCM credential vault; opaque hashed sessions/keys."""
import os
import time
import base64
import secrets
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

ph = PasswordHasher()

def hash_password(password):
    if len(password) < 12:
        raise ValueError("Mật khẩu phải có ít nhất 12 ký tự")
    return ph.hash(password)

def verify_password(hash_value, password):
    try:
        return ph.verify(hash_value, password)
    except (VerifyMismatchError, VerificationError):
        return False

def hash_secret(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def make_secret(prefix=''):
    return prefix + secrets.token_urlsafe(36)

def master_key():
    s = os.environ.get('MASTER_KEY', '')
    try:
        raw = base64.b64decode(s, validate=True)
    except Exception:
        raw = b''
    if len(raw) != 32:
        raise RuntimeError('MASTER_KEY phải là chuỗi base64 của 32 bytes (xem README)')
    return raw

def validate_secrets():
    master_key()
    if len(os.environ.get('SESSION_SECRET', '')) < 32:
        raise RuntimeError('SESSION_SECRET phải có tối thiểu 32 ký tự')

def seal(value, aad):
    nonce = os.urandom(12)
    encrypted = AESGCM(master_key()).encrypt(nonce, value.encode('utf-8'), aad.encode('utf-8'))
    return base64.urlsafe_b64encode(nonce + encrypted).decode('ascii')

def unseal(value, aad):
    blob = base64.urlsafe_b64decode(value)
    return AESGCM(master_key()).decrypt(blob[:12], blob[12:], aad.encode('utf-8')).decode('utf-8')

# ---------------------------------------------------------------------------
# Durable failed-attempt throttling for sensitive actions (2026-10-21).
#
# Login already has its own durable counters in app.py (login_attempts).
# The other secret-checking endpoints — license activation, password change,
# MFA enable/disable — verify a secret but had NO attempt limit at all, so a
# stolen session (or a malicious insider process) could guess indefinitely.
# This generic helper mirrors the proven login pattern: a SQLite table in
# the shared database (survives restarts, shared across processes), a
# sliding window count, and an immediate commit on failure because callers
# raise HTTPException, which would otherwise roll the counter back.
#
# Usage at a call site (db is an open ads_core.db.connection()):
#   scope = license_activation_scope(ident['id'])
#   if attempt_blocked(db, scope, LICENSE_ACTIVATION_MAX_ATTEMPTS):
#       raise HTTPException(429, '...')
#   if not <secret valid>:
#       attempt_failed(db, scope)
#       raise HTTPException(...)
#   attempt_succeeded(db, scope)
# ---------------------------------------------------------------------------
ATTEMPT_WINDOW_SECONDS = 900

def _attempts_init(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS guarded_attempts (
        scope TEXT NOT NULL,
        attempted_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_guarded_attempts_scope
        ON guarded_attempts(scope, attempted_at);
    ''')

def attempt_count(db, scope, window=ATTEMPT_WINDOW_SECONDS, now=None):
    _attempts_init(db)
    now = time.time() if now is None else now
    row = db.execute('SELECT COUNT(*) c FROM guarded_attempts WHERE scope=? AND attempted_at>?',
                     (scope, int(now) - window)).fetchone()
    return row['c']

def attempt_blocked(db, scope, limit, window=ATTEMPT_WINDOW_SECONDS, now=None):
    return attempt_count(db, scope, window=window, now=now) >= limit

def attempt_failed(db, scope, now=None):
    _attempts_init(db)
    now = time.time() if now is None else now
    db.execute('INSERT INTO guarded_attempts(scope, attempted_at) VALUES(?,?)',
               (scope, int(now)))
    # Opportunistic prune so the table cannot grow without bound.
    db.execute('DELETE FROM guarded_attempts WHERE attempted_at<?', (int(now) - 86400,))
    # Commit immediately: the caller raises HTTPException for the failed
    # attempt, which would otherwise roll this counter back.
    db.commit()

def attempt_succeeded(db, scope):
    _attempts_init(db)
    db.execute('DELETE FROM guarded_attempts WHERE scope=?', (scope,))

# Ready-made scopes and limits for the sensitive endpoints. Limits are per
# authenticated user: generous for a human re-typing or re-pasting, useless
# for automated guessing.
LICENSE_ACTIVATION_MAX_ATTEMPTS = 10

def license_activation_scope(user_id):
    return f'license-activate:user:{user_id}'

PASSWORD_CHANGE_MAX_ATTEMPTS = 5

def password_change_scope(user_id):
    return f'password-change:user:{user_id}'

MFA_MAX_ATTEMPTS = 5

def mfa_scope(user_id, action):
    return f'mfa-{action}:user:{user_id}'
