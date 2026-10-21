"""Integration wiring added by the coordinator after the 10-agent
commercial sprint: revocation consulted by read_license/activate_license,
durable throttling on license activation, password change and MFA, and
the vendor ledger einvoice-status command. Offline only."""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import licensing


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'data' / 'db.sqlite'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'k' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'a' * 48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.delenv('LHM_REVOCATION_FILE', raising=False)
    with TestClient(app) as c:
        with connection() as db:
            db.execute("INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)",
                       ('wiring@example.test', hash_password('long_password_123'), 'org-main', 'admin'))
        yield c


def login(client):
    r = client.post('/api/login', json={'email': 'wiring@example.test', 'password': 'long_password_123'})
    assert r.status_code == 200
    return {'X-CSRF-Token': client.get('/api/me').json()['csrf']}


def keypair(monkeypatch):
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                         format=serialization.PublicFormat.Raw)
    monkeypatch.setattr(licensing, 'PUBLIC_KEY_B64', base64.b64encode(pub).decode())
    return key


def signed_license(key, device, license_id='test-license-123', days=30):
    ts = int(time.time())
    payload = {'product': licensing.PRODUCT, 'device': device, 'plan': 'monthly',
               'license_id': license_id, 'issued_at': ts - 10, 'expires_at': ts + days * 86400}
    return json.dumps({'payload': payload,
                       'signature': base64.b64encode(key.sign(licensing.canonical(payload))).decode()})


def write_revocation_list(key, entries):
    # The revocation module verifies a detached signature over the EXACT
    # bytes of the list file (not a canonical form) — sign what we write.
    folder = licensing.license_folder()
    folder.mkdir(parents=True, exist_ok=True)
    doc = {'version': 1, 'issued_at': int(time.time()), 'entries': entries}
    raw = json.dumps(doc).encode('utf-8')
    (folder / 'revocations.json').write_bytes(raw)
    sig = base64.b64encode(key.sign(raw)).decode()
    (folder / 'revocations.json.sig').write_text(sig, encoding='ascii')
    return folder


def test_revoked_license_cannot_activate(client, monkeypatch):
    key = keypair(monkeypatch)
    h = login(client)
    device = client.get('/api/license').json()['device']
    write_revocation_list(key, [{'license_id': 'test-license-123',
                                 'reason': 'Hoàn tiền theo yêu cầu',
                                 'revoked_at': int(time.time())}])
    r = client.post('/api/license/activate', headers=h,
                    json={'license_text': signed_license(key, device)})
    assert r.status_code == 422
    assert 'đã bị thu hồi' in r.json()['detail']
    assert client.get('/api/license').json()['active'] is False


def test_revocation_deactivates_existing_license(client, monkeypatch):
    key = keypair(monkeypatch)
    h = login(client)
    device = client.get('/api/license').json()['device']
    r = client.post('/api/license/activate', headers=h,
                    json={'license_text': signed_license(key, device)})
    assert r.status_code == 200 and r.json()['active'] is True
    write_revocation_list(key, [{'device_id': device, 'reason': 'Đổi máy',
                                 'revoked_at': int(time.time())}])
    status = client.get('/api/license').json()
    assert status['active'] is False and status['reason'] == 'revoked'


def test_tampered_revocation_list_fails_closed(client, monkeypatch):
    key = keypair(monkeypatch)
    h = login(client)
    device = client.get('/api/license').json()['device']
    r = client.post('/api/license/activate', headers=h,
                    json={'license_text': signed_license(key, device)})
    assert r.status_code == 200 and r.json()['active'] is True
    folder = write_revocation_list(key, [])
    (folder / 'revocations.json').write_text('{"version":1,"issued_at":1,"entries":[]}',
                                             encoding='utf-8')  # signature no longer matches
    status = client.get('/api/license').json()
    assert status['active'] is False and status['reason'] == 'revocation_list_invalid'


def test_activation_throttle_after_repeated_failures(client, monkeypatch):
    keypair(monkeypatch)
    h = login(client)
    bad = json.dumps({'payload': {}, 'signature': 'AAAA'})
    codes = [client.post('/api/license/activate', headers=h,
                         json={'license_text': bad + ' ' * 60}).status_code
             for _ in range(11)]
    assert 429 in codes, codes


def test_vendor_ledger_einvoice_status(tmp_path):
    import subprocess
    import sys
    out = subprocess.run([sys.executable, 'tools/vendor_ledger.py', '--db',
                          str(tmp_path / 'ledger.sqlite3'), 'einvoice-status'],
                         capture_output=True, text=True, encoding='utf-8', errors='strict', cwd=str(_repo_root()))
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout)
    assert result['einvoice_configured'] is False


def test_seller_clis_survive_windows_legacy_codepage(tmp_path):
    """Regression: the Windows CI job runs pytest on Windows, where a piped
    stdout defaults to cp1252 and cannot encode Vietnamese — the seller CLIs
    crashed with UnicodeEncodeError (windows-exe job failure, 2026-10-21).
    Every CLI now pins its streams to UTF-8; simulate with
    PYTHONIOENCODING=cp1252, which has the same effect on Linux."""
    import os
    import subprocess
    import sys
    env = dict(os.environ, PYTHONIOENCODING='cp1252')
    out = subprocess.run([sys.executable, 'tools/vendor_ledger.py', '--db',
                          str(tmp_path / 'ledger.sqlite3'), 'einvoice-status'],
                         capture_output=True, text=True, encoding='utf-8', errors='strict', cwd=str(_repo_root()), env=env)
    assert out.returncode == 0, out.stderr
    assert 'hóa đơn' in out.stdout
    env.update({'DB_PATH': str(tmp_path / 'd' / 'db.sqlite'),
                'MASTER_KEY': base64.b64encode(b'k' * 32).decode(),
                'SESSION_SECRET': 'a' * 48})
    out = subprocess.run([sys.executable, 'tools/acceptance_preflight.py'],
                         capture_output=True, text=True, encoding='utf-8', errors='strict', cwd=str(_repo_root()), env=env)
    assert out.returncode == 0, out.stderr
    assert 'Tổng kết' in out.stdout


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]
