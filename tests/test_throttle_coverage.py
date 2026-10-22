"""Throttle coverage audit round 2 (2026-10-22).

Round 1 guarded login, license activation, password change and MFA
enable/disable. The audit of every remaining sensitive POST endpoint
(see SUMMARY.md of sprint20/a16) found exactly one more endpoint that
verifies a secret with no attempt limit: POST /api/desktop/first-run,
which checks the one-time setup token before any user exists. These
tests prove its new durable guarded_attempts throttle (keyed by client
IP): 429 after the limit, the correct token is also refused while
blocked, counters are per-IP, success clears the counter, and the
sliding window expires. All offline.
"""
import base64

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core import desktop_onboarding as onboarding
from ads_core.security import (
    ATTEMPT_WINDOW_SECONDS, FIRST_RUN_MAX_ATTEMPTS, attempt_blocked,
    attempt_count, attempt_failed, first_run_scope,
)

GOOD = {'email': 'owner@shop.vn', 'password': 'some_secure_password_123'}
BAD_TOKEN = 'w' * 50


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'throttle2.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'U' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'S' * 48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('LHM_DESKTOP_MODE', '1')
    token = onboarding.prepare_first_run()
    assert token
    yield token
    onboarding.TOKEN = None
    onboarding.TOKEN_EXPIRES_AT = 0


def _client(ip):
    return TestClient(app, client=(ip, 50000))


def test_first_run_429_after_limit_and_correct_token_also_refused(setup_env):
    token = setup_env
    with _client('127.0.0.1') as c:
        for _ in range(FIRST_RUN_MAX_ATTEMPTS):
            r = c.post('/api/desktop/first-run', json={**GOOD, 'token': BAD_TOKEN})
            assert r.status_code == 403, r.text
        # Limit reached: the next guess is refused before any token check.
        r = c.post('/api/desktop/first-run', json={**GOOD, 'token': BAD_TOKEN})
        assert r.status_code == 429, r.text
        # Even the CORRECT token is refused while the window is saturated:
        # the throttle is a gate, not an oracle for the right answer.
        r = c.post('/api/desktop/first-run', json={**GOOD, 'token': token})
        assert r.status_code == 429, r.text
    with connection() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


def test_first_run_throttle_is_keyed_per_ip(setup_env):
    token = setup_env
    with _client('127.0.0.1') as c4:
        for _ in range(FIRST_RUN_MAX_ATTEMPTS):
            assert c4.post('/api/desktop/first-run',
                           json={**GOOD, 'token': BAD_TOKEN}).status_code == 403
        assert c4.post('/api/desktop/first-run',
                       json={**GOOD, 'token': token}).status_code == 429
    # A different loopback source has its own counter and can still set up.
    with _client('::1') as c6:
        r = c6.post('/api/desktop/first-run', json={**GOOD, 'token': token})
        assert r.status_code == 200, r.text


def test_first_run_success_clears_counter(setup_env):
    token = setup_env
    with _client('127.0.0.1') as c:
        for _ in range(3):
            assert c.post('/api/desktop/first-run',
                          json={**GOOD, 'token': BAD_TOKEN}).status_code == 403
        with connection() as db:
            assert attempt_count(db, first_run_scope('127.0.0.1')) == 3
        r = c.post('/api/desktop/first-run', json={**GOOD, 'token': token})
        assert r.status_code == 200, r.text
    with connection() as db:
        assert attempt_count(db, first_run_scope('127.0.0.1')) == 0


def test_first_run_scope_keying_and_window_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'unit.sqlite3'))
    # Scopes never collide across IPs or with the per-user scopes of round 1.
    assert first_run_scope('127.0.0.1') != first_run_scope('::1')
    assert first_run_scope('127.0.0.1').startswith('first-run:ip:')
    with connection() as db:
        scope = first_run_scope('127.0.0.1')
        for i in range(FIRST_RUN_MAX_ATTEMPTS):
            attempt_failed(db, scope, now=1000 + i)
        assert attempt_blocked(db, scope, FIRST_RUN_MAX_ATTEMPTS, now=1010)
        assert not attempt_blocked(db, first_run_scope('::1'),
                                   FIRST_RUN_MAX_ATTEMPTS, now=1010)
        later = 1000 + ATTEMPT_WINDOW_SECONDS + 1
        assert not attempt_blocked(db, scope, FIRST_RUN_MAX_ATTEMPTS, now=later)
