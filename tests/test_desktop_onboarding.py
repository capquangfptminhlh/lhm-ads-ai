"""First-run UI for the local Windows EXE is graphical and securely token-guarded."""
import base64
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core.db import connection
from ads_core import desktop_onboarding as onboarding

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'onboarding.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'U'*32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'S'*48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('LHM_DESKTOP_MODE', '1')
    token = onboarding.prepare_first_run()
    with TestClient(app, client=('127.0.0.1', 50000)) as c:
        yield c, token
    onboarding.TOKEN = None
    onboarding.TOKEN_EXPIRES_AT = 0

def test_first_run_ui_and_login_session(client):
    c, token = client
    page = c.get('/setup')
    assert page.status_code == 200
    assert 'Tạo tài khoản quản trị' in page.text
    assert '/static/setup.js' in page.text
    assert c.get('/static/setup.css').status_code == 200
    assert c.get('/static/setup.js').status_code == 200
    assert c.get('/api/accounts').status_code == 401
    reply = c.post('/api/desktop/first-run', json={
        'email': 'owner@myshop.vn', 'password': 'some_secure_password_123', 'token': token})
    assert reply.status_code == 200, reply.text
    assert c.get('/api/me').json()['email'] == 'owner@myshop.vn'
    assert c.get('/setup', follow_redirects=False).status_code == 303
    assert c.post('/api/desktop/first-run', json={
        'email': 'two@shop.vn', 'password': 'some_secure_password_123',
        'token': token}).status_code == 403

def test_invalid_token_rejected(client):
    c, token = client
    assert c.post('/api/desktop/first-run', json={
        'email': 'owner@shop.vn', 'password': 'some_secure_password_123',
        'token': 'w'*50}).status_code == 403
    with connection() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0

def test_setup_disabled_when_not_desktop(client, monkeypatch):
    c, token = client
    monkeypatch.delenv('LHM_DESKTOP_MODE')
    assert c.get('/setup').status_code == 404
    assert c.post('/api/desktop/first-run', json={
        'email': 'owner@shop.vn', 'password': 'some_secure_password_123',
        'token': token}).status_code == 404

def test_password_is_hashed(client):
    c, token = client
    pwd = 'some_secure_password_123'
    assert c.post('/api/desktop/first-run', json={
        'email': 'owner@shop.vn', 'password': pwd, 'token': token}).status_code == 200
    with connection() as db:
        row = db.execute('SELECT password_hash FROM users').fetchone()
        assert pwd not in row['password_hash']

def test_existing_user_cannot_reissue_setup_token(client):
    c, token = client
    assert c.post('/api/desktop/first-run', json={
        'email': 'owner@shop.vn', 'password': 'some_secure_password_123',
        'token': token}).status_code == 200
    assert onboarding.prepare_first_run() is None
    assert onboarding.TOKEN is None

def test_windows_workflow_builds_windowed_exe():
    root = Path(__file__).resolve().parent.parent
    workflow = (root/'.github/workflows/windows-exe.yml').read_text(encoding='utf-8')
    launcher = (root/'windows/launcher.py').read_text(encoding='utf-8')
    assert '--windowed' in workflow
    assert 'getpass.getpass(' not in launcher
    assert '/setup#token=' in launcher
    assert "host='127.0.0.1'" in launcher
