"""Offline tests: Windows local-only provider configuration, never call Google or Meta."""
import base64
import os
from urllib.parse import parse_qs,urlparse
import pytest
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import oauth_connect

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('LHM_DESKTOP_MODE','1')
    monkeypatch.setenv('DB_PATH',str(tmp_path/'db.sqlite3'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'b'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','a'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setenv('PUBLIC_BASE_URL','http://localhost:18765')
    # Desktop mode MUST NOT inherit credentials configured on a shared web server.
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID','env-web-client.apps.googleusercontent.com')
    monkeypatch.setenv('META_APP_ID','111111')
    with TestClient(app,base_url='http://localhost:18765') as c:
        with connection() as db:
            for email,org in [('main@test.local','first'),('other@test.local','second')]:
                db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                           (email,hash_password('very_secret_password_999'),org,'admin'))
        yield c

def logged(client,email='main@test.local'):
    assert client.post('/api/login',json={'email':email,'password':'very_secret_password_999'}).status_code==200
    return {'X-CSRF-Token':client.get('/api/me').json()['csrf']}

def test_desktop_only_google_config_and_pkce(client):
    h=logged(client)
    status=client.get('/api/oauth/status').json()
    assert not status['google']['configured']
    assert status['google']['callback_url']=='http://localhost:18765/api/oauth/google/callback'
    assert client.put('/api/desktop/providers/google',json={'client_id':'9876543210-xyz.apps.googleusercontent.com'}).status_code==403
    r=client.put('/api/desktop/providers/google',headers=h,json={'client_id':'9876543210-xyz.apps.googleusercontent.com'})
    assert r.status_code==200,r.text
    assert r.json()['google']['configured']
    raw=client.get('/api/desktop/providers').text
    assert 'env-web-client' not in raw
    start=client.post('/api/oauth/google/start',headers=h)
    assert start.status_code==200,start.text
    query=parse_qs(urlparse(start.json()['authorization_url']).query)
    assert query['redirect_uri']==['http://localhost:18765/api/oauth/google/callback']
    assert query['code_challenge_method']==['S256']
    assert query['client_id']==['9876543210-xyz.apps.googleusercontent.com']
    assert not client.get('/api/desktop/providers').json()['google']['secret_saved']

def test_meta_secret_encrypted_and_delete(client):
    h=logged(client)
    bad=client.put('/api/desktop/providers/meta',headers=h,json={'client_id':'1234567'})
    assert bad.status_code==422
    save=client.put('/api/desktop/providers/meta',headers=h,json={'client_id':'1234567','client_secret':'super-secret-app-key-1234'})
    assert save.status_code==200,save.text
    assert 'super-secret-app-key-1234' not in save.text
    with connection() as db:
        row=db.execute("SELECT secret_ciphertext FROM desktop_app_credentials WHERE platform='meta'").fetchone()
    assert 'super-secret-app-key-1234' not in row[0]
    a=client.post('/api/oauth/meta/start',headers=h)
    assert a.status_code==200
    assert 'super-secret-app-key-1234' not in a.text
    assert client.delete('/api/desktop/providers/meta',headers=h).status_code==200
    assert client.post('/api/oauth/meta/start',headers=h).status_code==422

def test_session_bound_tenant_and_server_route_disabled(client,monkeypatch):
    h=logged(client)
    assert client.put('/api/desktop/providers/google',headers=h,json={'client_id':'1234567890-aaa.apps.googleusercontent.com'}).status_code==200
    client.post('/api/logout',headers=h)
    logged(client,'other@test.local')
    assert client.get('/api/desktop/providers').json()['google']['configured'] is False
    assert client.get('/api/oauth/status').json()['google']['configured'] is False
    monkeypatch.delenv('LHM_DESKTOP_MODE')
    assert client.get('/api/desktop/providers').status_code==404

def test_windows_launcher_uses_loopback_and_browser_localhost():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    script=(root/'windows/launcher.py').read_text(encoding='utf8')
    assert "host='127.0.0.1'" in script
    assert "'LHM_DESKTOP_MODE'" in script
    assert 'http://localhost:{args.port}' in script
    html=(root/'static/studio.html').read_text(encoding='utf8')
    for key in ['desktop-google-form','desktop-meta-form','desktop-provider-panel']:
        assert key in html
