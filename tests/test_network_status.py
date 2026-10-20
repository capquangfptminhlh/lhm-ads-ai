"""Offline tests: Internet status has no Ads token dependency and respects login."""
import base64
import pytest
from fastapi.testclient import TestClient
from ads_core.db import connection
from ads_core.extended import app
from ads_core.security import hash_password
from ads_core import network_status as net

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'network.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'N'*32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'R'*48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    net.CACHE['checked_at'] = -float('inf')
    net.CACHE['online'] = False
    with TestClient(app) as c:
        with connection() as db:
            db.execute(
                'INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)',
                ('local@sample.test', hash_password('secure_password_123'), 'test', 'admin')
            )
        yield c

def login(client):
    assert client.post('/api/login', json={
        'email':'local@sample.test','password':'secure_password_123'
    }).status_code == 200

def test_probe_is_protected_by_login(client, monkeypatch):
    async def forbidden():
        raise AssertionError('Should not probe when not logged in')
    monkeypatch.setattr(net, 'probe_internet', forbidden)
    assert client.get('/api/network/status').status_code == 401

def test_network_status_cached_and_recovers(client, monkeypatch):
    login(client)
    calls = []
    async def probe():
        calls.append(True)
        return len(calls) > 1
    monkeypatch.setattr(net, 'probe_internet', probe)
    r = client.get('/api/network/status')
    assert r.status_code == 200
    assert r.json()['online'] is False
    assert client.get('/api/network/status').json()['online'] is False
    assert len(calls) == 1
    net.CACHE['checked_at'] = -float('inf')
    assert client.get('/api/network/status').json()['online'] is True
    assert len(calls) == 2

def test_probes_no_secrets_and_fallback(monkeypatch):
    urls=[]
    class Response:
        def __init__(self, code): self.status_code=code
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['follow_redirects'] is False
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return False
        async def head(self,url):
            urls.append(url)
            return Response(204 if url.endswith('generate_204') else 200)
    monkeypatch.setattr(net.httpx, 'AsyncClient', Client)
    import asyncio
    assert asyncio.run(net.probe_internet())
    assert urls == ['https://www.google.com/generate_204']

def test_frontend_status_not_static():
    from pathlib import Path
    root=Path(__file__).resolve().parent.parent
    html=(root/'static/studio.html').read_text(encoding='utf-8')
    js=(root/'static/studio.js').read_text(encoding='utf-8')
    assert 'id="network-status"' in html
    assert 'SYSTEM ONLINE' not in html
    assert "api('/api/network/status')" in js
    assert "beginNetworkMonitor()" in js
    assert '/mcp' not in {r.path for r in app.router.routes}
