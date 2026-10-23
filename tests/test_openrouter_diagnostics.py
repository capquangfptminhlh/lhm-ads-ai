"""Non-billable local OpenRouter checks: no prompt, no token leak, correct ZDR/licensing."""
import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core import openrouter_ai as ai
from ads_core.db import connection
from ads_core.security import hash_password

KEY = 'sk-or-v1-' + 't'*40
MODEL = 'deepseek/deepseek-v4.1-flash-1017'


@pytest.fixture
def admin(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'diagnose.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'e'*32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'diagnostic-test-strong-session-42')
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('LHM_DESKTOP_MODE', '1')
    from ads_core import licensing
    monkeypatch.setattr(licensing, 'read_license',
                        lambda: {'active': True, 'reason': 'active'})
    with TestClient(app) as client:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       ('admin@test.invalid',hash_password('safe_password_1234'),'org-diagnostic','admin'))
        response=client.post('/api/login',json={'email':'admin@test.invalid',
                                                  'password':'safe_password_1234'})
        assert response.status_code==200
        h={'X-CSRF-Token':client.get('/api/studio/me').json()['csrf']}
        yield client, h


def configured(client, h, *, model=MODEL):
    r=client.put('/api/ai/settings',headers=h,
                 json={'api_key':KEY,'model':model,'enabled':True,'daily_limit':1})
    assert r.status_code == 200, r.text


def mock_provider(monkeypatch, *, key_code=200, present=True, zdr=True, remaining=10):
    calls=[]
    class Response:
        def __init__(self, code, data):self.status_code=code;self.data=data
        def json(self):return self.data
    class Client:
        def __init__(self,*args,**kwargs):
            assert kwargs['trust_env'] is False
            assert kwargs['follow_redirects'] is False
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return False
        async def get(self, url, headers, params=None):
            calls.append((url,headers,params))
            assert headers['Authorization']=='Bearer '+KEY
            if url.endswith('/key'):
                return Response(key_code, {'data': {'limit_remaining':remaining}})
            assert url.endswith('/models')
            found=present and (not params.get('zdr') or zdr)
            return Response(200, {'data':[{'id':MODEL}] if found else []})
    monkeypatch.setattr(ai.httpx, 'AsyncClient', Client)
    return calls


def test_requires_admin_csrf_and_never_calls_provider_without_key(admin, monkeypatch):
    client,h=admin
    assert client.post('/api/ai/diagnostics').status_code==403
    async def bad(*args,**kwargs):raise AssertionError('No configured key; no calls')
    monkeypatch.setattr(ai.httpx, 'AsyncClient', bad)
    r=client.post('/api/ai/diagnostics',headers=h,json={})
    assert r.status_code==200 and r.json()['key_status']=='not_configured'
    assert r.json()['chat_tested'] is False and not r.json()['ready_for_ai']


def test_key_and_zdr_are_checked_without_chat_request_or_quota(admin, monkeypatch):
    client,h=admin
    configured(client,h)
    calls=mock_provider(monkeypatch)
    result=client.post('/api/ai/diagnostics',headers=h,json={})
    assert result.status_code==200,result.text
    data=result.json()
    assert data['key_status']=='valid'
    assert data['model_status']=='zdr_available'
    assert data['ready_for_ai'] is True
    assert data['chat_tested'] is False
    assert data['used_today']==0 and data['daily_limit']==1
    assert len(calls)==3
    assert calls[0][0].endswith('/key')
    assert calls[1][2]=={'q':MODEL}
    assert calls[2][2]=={'q':MODEL,'zdr':'true'}
    assert KEY not in result.text
    assert client.get('/api/ai/settings').json()['used_today']==0


def test_invalid_key_stops_before_model_check(admin, monkeypatch):
    client,h=admin
    configured(client,h)
    calls=mock_provider(monkeypatch,key_code=401)
    result=client.post('/api/ai/diagnostics',headers=h,json={}).json()
    assert result['key_status']=='invalid'
    assert result['model_status']=='not_checked'
    assert not result['ready_for_ai']
    assert len(calls)==1
    assert KEY not in str(result)


def test_model_without_zdr_is_not_routable_under_current_policy(admin, monkeypatch):
    client,h=admin
    configured(client,h)
    mock_provider(monkeypatch,zdr=False)
    result=client.post('/api/ai/diagnostics',headers=h,json={}).json()
    assert result['key_status']=='valid'
    assert result['model_status']=='zdr_unavailable'
    assert not result['ready_for_ai']


def test_license_and_daily_limit_are_not_bypassed(admin,monkeypatch):
    client,h=admin
    configured(client,h)
    from ads_core import licensing
    monkeypatch.setattr(licensing,'read_license',lambda: {'active':False,'reason':'expired'})
    mock_provider(monkeypatch)
    result=client.post('/api/ai/diagnostics',headers=h,json={}).json()
    assert not result['license']['active']
    assert result['license']['reason']=='expired'
    assert result['key_status']=='valid'
    assert result['model_status']=='zdr_available'
    assert not result['ready_for_ai']


def test_connection_error_is_sanitized(admin,monkeypatch):
    import httpx
    client,h=admin
    configured(client,h)
    class Client:
        def __init__(self,*a,**k):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):return False
        async def get(self,*a,**k):
            raise httpx.ConnectError('credential '+KEY+' unreachable')
    monkeypatch.setattr(ai.httpx,'AsyncClient',Client)
    r=client.post('/api/ai/diagnostics',headers=h,json={})
    assert r.status_code==200
    assert r.json()['key_status']=='network_error'
    assert KEY not in r.text


def test_onboarding_ui_contains_no_credentials_or_auto_paid_request():
    root=Path(__file__).resolve().parents[1]/'static'
    html=(root/'studio.html').read_text(encoding='utf-8')
    js=(root/'openrouter-diagnostics.js').read_text(encoding='utf-8')
    css=(root/'openrouter-diagnostics.css').read_text(encoding='utf-8')
    assert '/static/openrouter-diagnostics.css' in html
    assert '/static/openrouter-diagnostics.js' in html
    assert "api('/api/ai/diagnostics',{method:'POST'" in js
    assert 'data-or-check' in js
    assert 'chat_tested' not in js or 'Đã xác minh key' in js
    assert 'không phải thử sinh câu trả lời' in js.lower() or 'KHÔNG phải thử sinh câu trả lời' in js
    assert 'api_key' not in js and 'window.localStorage' not in js
    assert '@media(max-width:620px)' in css
