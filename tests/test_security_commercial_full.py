"""MFA TOTP, durable login throttling and seller renewal reminders."""
from __future__ import annotations

import base64
import importlib.util
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ads_core import mfa as mfa_module
from ads_core.db import connection
from ads_core.extended import app
from ads_core.security import hash_password, unseal

EMAIL = "admin@a.test"
PASSWORD = "secure_pass_1234"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'ads.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'x' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'a' * 48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       (EMAIL, hash_password(PASSWORD), 'A', 'admin'))
        yield c


def _login(client, **extra):
    return client.post('/api/login', json={'email': EMAIL, 'password': PASSWORD, **extra})


def _headers(client):
    return {'X-CSRF-Token': client.get('/api/me').json()['csrf']}


def _wrong_code(secret: str) -> str:
    valid = {mfa_module.totp(secret, int(time.time()) + drift * 30)
             for drift in (0, -1, 1)}
    for candidate in ("000000", "111111", "222222", "999999"):
        if candidate not in valid:
            return candidate
    raise AssertionError("no wrong code candidate available")


def _enable_mfa(client) -> str:
    assert _login(client).status_code == 200
    headers = _headers(client)
    setup = client.post("/api/me/mfa/setup", headers=headers, json={})
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    enabled = client.post("/api/me/mfa/enable", headers=headers,
                          json={"code": mfa_module.totp(secret)})
    assert enabled.status_code == 200, enabled.text
    return secret


def test_mfa_lifecycle_and_login_gate(client):
    secret = _enable_mfa(client)
    status = client.get("/api/me/mfa", headers=_headers(client))
    assert status.json()["enabled"] is True

    fresh = TestClient(app)
    no_code = _login(fresh)
    assert no_code.status_code == 401
    assert "mfa_required" in no_code.json()["detail"]
    assert fresh.cookies.get("lhm_session") is None

    bad = _login(fresh, totp=_wrong_code(secret))
    assert bad.status_code == 401

    ok = _login(fresh, totp=mfa_module.totp(secret))
    assert ok.status_code == 200, ok.text


def test_mfa_enable_requires_valid_code_and_disable_requires_both(client):
    assert _login(client).status_code == 200
    headers = _headers(client)
    client.post("/api/me/mfa/setup", headers=headers, json={})
    with connection() as db:
        row = db.execute("SELECT user_id, secret_ciphertext FROM user_mfa").fetchone()
    secret = unseal(row["secret_ciphertext"], f"mfa:{row['user_id']}")
    bad = client.post("/api/me/mfa/enable", headers=headers,
                      json={"code": _wrong_code(secret)})
    assert bad.status_code == 403
    good = client.post("/api/me/mfa/enable", headers=headers,
                       json={"code": mfa_module.totp(secret)})
    assert good.status_code == 200
    wrong_pass = client.post("/api/me/mfa/disable", headers=headers, json={
        "password": "not-the-password", "code": mfa_module.totp(secret)})
    assert wrong_pass.status_code == 403
    disabled = client.post("/api/me/mfa/disable", headers=headers, json={
        "password": PASSWORD, "code": mfa_module.totp(secret)})
    assert disabled.status_code == 200, disabled.text
    # After disabling, plain password login works again.
    assert _login(TestClient(app)).status_code == 200


def test_login_throttle_is_durable_in_database(client):
    # Five failures for the same email lock that email out (429), and the
    # counters live in SQLite so a restart cannot reset them.
    for _ in range(5):
        r = client.post("/api/login", json={
            "email": EMAIL, "password": "definitely-wrong-1"})
        assert r.status_code == 401
    blocked = _login(client)
    assert blocked.status_code == 429
    with connection() as db:
        count = db.execute(
            "SELECT COUNT(*) c FROM login_attempts WHERE scope=?",
            (f"email:{EMAIL}",)).fetchone()["c"]
    assert count >= 5


def test_totp_window_tolerance():
    secret = "JBSWY3DPEHPK3PXP"
    now = 1_700_000_040  # exact step boundary
    code = mfa_module.totp(secret, now)
    assert len(code) == 6 and code.isdigit()
    assert mfa_module.verify_totp(secret, code, now)
    assert mfa_module.verify_totp(secret, code, now + 30)   # previous-step window
    assert not mfa_module.verify_totp(secret, code, now + 300)


# ---------------------------------------------------------------- vendor tool

spec = importlib.util.spec_from_file_location(
    "vendor_ledger_full", Path(__file__).resolve().parents[1] / "tools" / "vendor_ledger.py")
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def _insert_license(db, ref, device, lid, issued, expiry, now, status="confirmed"):
    db.execute("""INSERT INTO licenses(license_id,customer_ref,device,plan,
        issued_at,expires_at,signature_sha256,payment_status,recorded_at)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (lid, ref, device, "monthly", issued, expiry, "x" * 64, status, now))
    db.commit()


def test_vendor_remind_selects_only_expiring_and_expired(tmp_path):
    db = ledger.connect(tmp_path / "vendor.sqlite3")
    now = 1_800_000_000
    ledger.register(db, "KH001", "a" * 32, now=now)
    ledger.register(db, "KH002", "b" * 32, now=now)
    _insert_license(db, "KH001", "a" * 32, "LIC-0001", now - 27 * 86400, now + 3 * 86400, now)
    _insert_license(db, "KH002", "b" * 32, "LIC-0002", now - 27 * 86400, now + 60 * 86400, now)
    result = ledger.remind(db, within_days=7, now=now)
    assert result["count"] == 1
    assert result["reminders"][0]["customer_ref"] == "KH001"
    assert result["reminders"][0]["state"] == "expiring"
    assert "KH001" in result["message"] and "KH002" not in result["message"]
    assert result["sent"] is False


def test_vendor_remind_send_uses_injected_transport(tmp_path):
    db = ledger.connect(tmp_path / "vendor.sqlite3")
    now = 1_800_000_000
    ledger.register(db, "KH009", "c" * 32, now=now)
    _insert_license(db, "KH009", "c" * 32, "LIC-0009", now - 40 * 86400,
                    now - 86400, now, status="pending")
    sent = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode()

    def opener(request, timeout=None):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data.decode())
        return _Response()

    result = ledger.remind(db, within_days=7, send=True,
                           environ={"VENDOR_TELEGRAM_BOT_TOKEN": "tok",
                                    "VENDOR_TELEGRAM_CHAT_ID": "42"},
                           opener=opener, now=now)
    assert result["sent"] is True
    assert sent["url"] == "https://api.telegram.org/bottok/sendMessage"
    assert sent["body"]["chat_id"] == "42"
    assert "KH009" in sent["body"]["text"]

    # Missing seller Telegram configuration must fail loudly, never silently.
    with pytest.raises(ValueError, match="VENDOR_TELEGRAM"):
        ledger.remind(db, within_days=7, send=True, environ={}, opener=opener, now=now)
