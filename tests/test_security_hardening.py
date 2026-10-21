"""Commercial security pass (2026-10-21): response-header hardening,
session-cookie flag consistency, and the durable guarded-attempts throttle
helper that the sensitive endpoints (license activation, password change,
MFA) wire into. All offline."""
import base64

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import (
    hash_password, attempt_blocked, attempt_count, attempt_failed,
    attempt_succeeded, license_activation_scope, password_change_scope,
    mfa_scope, LICENSE_ACTIVATION_MAX_ATTEMPTS, MFA_MAX_ATTEMPTS,
    ATTEMPT_WINDOW_SECONDS,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'ads.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'x' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'a' * 48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       ('admin@a.test', hash_password('secure_pass_1234'), 'A', 'admin'))
        yield c


# ---------------------------------------------------------------- headers

def test_security_headers_present(client):
    r = client.get('/healthz')
    assert r.headers['x-content-type-options'] == 'nosniff'
    assert r.headers['x-frame-options'] == 'DENY'
    assert r.headers['referrer-policy'] == 'no-referrer'
    assert r.headers['cache-control'] == 'no-store'
    csp = r.headers['content-security-policy']
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # Deliberate (bundled Inter font); must not be "cleaned up".
    assert "font-src 'self' data:" in csp
    assert "script-src 'self'" in csp
    pp = r.headers['permissions-policy']
    for feature in ('camera=()', 'microphone=()', 'geolocation=()',
                    'payment=()', 'usb=()'):
        assert feature in pp
    assert r.headers['cross-origin-resource-policy'] == 'same-origin'


def test_hsts_only_when_cookies_are_secure(client, monkeypatch):
    # Fixture runs with COOKIE_SECURE=false (desktop loopback HTTP mode):
    # no HSTS promise.
    assert 'strict-transport-security' not in client.get('/healthz').headers
    monkeypatch.setenv('COOKIE_SECURE', 'true')
    r = client.get('/healthz')
    assert r.headers['strict-transport-security'] == 'max-age=31536000'


# ---------------------------------------------------------------- cookies

def _set_cookie(client):
    r = client.post('/api/login', json={'email': 'admin@a.test',
                                        'password': 'secure_pass_1234'})
    assert r.status_code == 200, r.text
    return r.headers['set-cookie']


def test_session_cookie_flags_http_mode(client):
    cookie = _set_cookie(client).lower()
    assert 'lhm_session=' in cookie
    assert 'httponly' in cookie
    assert 'samesite=lax' in cookie
    assert 'secure' not in cookie  # COOKIE_SECURE=false in this mode


def test_session_cookie_secure_flag_follows_env(client, monkeypatch):
    monkeypatch.setenv('COOKIE_SECURE', 'true')
    cookie = _set_cookie(client).lower()
    assert 'httponly' in cookie
    assert 'samesite=lax' in cookie
    assert 'secure' in cookie


# ------------------------------------------------------- throttle helper

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'throttle.sqlite3'))
    with connection() as conn:
        yield conn


def test_attempt_throttle_blocks_at_limit(db):
    scope = license_activation_scope(7)
    assert not attempt_blocked(db, scope, LICENSE_ACTIVATION_MAX_ATTEMPTS, now=1000)
    for i in range(LICENSE_ACTIVATION_MAX_ATTEMPTS):
        attempt_failed(db, scope, now=1000 + i)
    assert attempt_count(db, scope, now=1010) == LICENSE_ACTIVATION_MAX_ATTEMPTS
    assert attempt_blocked(db, scope, LICENSE_ACTIVATION_MAX_ATTEMPTS, now=1010)


def test_attempt_throttle_scopes_are_isolated(db):
    attempt_failed(db, license_activation_scope(7), now=1000)
    assert attempt_count(db, license_activation_scope(8), now=1000) == 0
    assert attempt_count(db, password_change_scope(7), now=1000) == 0
    assert attempt_count(db, mfa_scope(7, 'enable'), now=1000) == 0


def test_attempt_throttle_window_expires(db):
    scope = password_change_scope(3)
    for _ in range(5):
        attempt_failed(db, scope, now=1000)
    assert attempt_blocked(db, scope, 5, now=1000)
    later = 1000 + ATTEMPT_WINDOW_SECONDS + 1
    assert not attempt_blocked(db, scope, 5, now=later)


def test_attempt_succeeded_clears_counter(db):
    scope = mfa_scope(5, 'disable')
    for _ in range(MFA_MAX_ATTEMPTS):
        attempt_failed(db, scope, now=2000)
    assert attempt_blocked(db, scope, MFA_MAX_ATTEMPTS, now=2000)
    attempt_succeeded(db, scope)
    assert attempt_count(db, scope, now=2000) == 0
    assert not attempt_blocked(db, scope, MFA_MAX_ATTEMPTS, now=2000)


def test_throttle_survives_new_connection(tmp_path, monkeypatch):
    # Durable means: a fresh connection (e.g. after a restart) still sees
    # the recorded failures — the counters live in SQLite, not in memory.
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'durable.sqlite3'))
    scope = license_activation_scope(1)
    with connection() as db1:
        for _ in range(LICENSE_ACTIVATION_MAX_ATTEMPTS):
            attempt_failed(db1, scope, now=3000)
    with connection() as db2:
        assert attempt_blocked(db2, scope, LICENSE_ACTIVATION_MAX_ATTEMPTS, now=3000)
