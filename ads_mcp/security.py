"""Argon2 passwords; AES-256-GCM credential vault; opaque hashed sessions/keys."""
import os
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
