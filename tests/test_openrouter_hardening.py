"""Privacy and quota guard tests use mocked networking only."""
import base64
import json
import pytest
from fastapi.testclient import TestClient
from ads_core.db import connection
from ads_core.extended import app
from ads_core.security import hash_password
from ads_core import openrouter_ai as ai

KEY = 'sk-or-v1-' + 'x' * 45

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'db.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'f'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','z'*50)
    monkeypatch.setenv('COOKIE_SECURE','false')
    ai.CALLS.clear()
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(org_id,email,role,password_hash) VALUES(?,?,?,?)',
                       ('org-x','boss@example.org','admin',hash_password('long-password-2026')))
        assert c.post('/api/login',json={'email':'boss@example.org','password':'long-password-2026'}).status_code==200
        yield c,{'X-CSRF-Token':c.get('/api/me').json()['csrf']}

def config(client,h,limit=3):
    r=client.put('/api/ai/settings',headers=h,json={'api_key':KEY,'model':'openai/gpt-4.1-mini',
                                                   'enabled':True,'daily_limit':limit})
    assert r.status_code==200,r.text
    return r.json()

class DummyResponse:
    status_code=200
    def json(self):
        return {'choices':[{'message':{'content':'Dự báo dựa vào CTR.'}}],
                'usage':{'prompt_tokens':8,'completion_tokens':5,'total_tokens':13}}

class DummyClient:
    calls=[]
    def __init__(self,*args,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return None
    async def post(self,url,headers,json):
        self.calls.append((url,headers,json))
        return DummyResponse()

def test_daily_quota_persistent_and_not_reset_by_read(client,monkeypatch):
    c,h=client
    config(c,h,limit=2)
    DummyClient.calls=[]
    monkeypatch.setattr(ai.httpx,'AsyncClient',DummyClient)
    for i in range(2):
        assert c.post('/api/assistant/chat',headers=h,json={'message':'Báo cáo chỉ số Ads'}).status_code==200
    assert len(DummyClient.calls)==2
    assert c.post('/api/assistant/chat',headers=h,json={'message':'Báo cáo chỉ số Ads'}).status_code==429
    state=c.get('/api/ai/settings').json()
    assert state['used_today']==2 and state['daily_limit']==2
    assert state['tokens_today']==26
    assert state['privacy']=='zdr_required'
    with connection() as db:
        assert db.execute('SELECT request_count FROM ai_daily_usage WHERE org_id=?',('org-x',)).fetchone()[0]==2


def test_zdr_and_minimized_payload(client,monkeypatch):
    c,h=client
    config(c,h)
    DummyClient.calls=[]
    monkeypatch.setattr(ai.httpx,'AsyncClient',DummyClient)
    data=c.post('/api/assistant/chat',headers=h,json={'message':'Gọi boss@company.vn, https://secret.example/path và 0912345678, ID 123456789012345678'}).json()
    assert data['mode']=='openrouter'
    request=DummyClient.calls[0][2]
    assert request['provider']=={'zdr':True,'data_collection':'deny'}
    outgoing=json.dumps(request,ensure_ascii=False)
    for value in ('boss@company.vn','https://secret.example/path','0912345678','123456789012345678'):
        assert value not in outgoing
    assert request['max_tokens']<=900


def test_preview_is_local_does_not_use_quota(client,monkeypatch):
    c,h=client
    config(c,h)
    def refuse(*args,**kwargs):raise AssertionError('preview must not access internet')
    monkeypatch.setattr(ai.httpx,'AsyncClient',refuse)
    r=c.post('/api/ai/preview',headers=h,json={'message':'Tài khoản test@example.com tiêu 500'} )
    assert r.status_code==200,r.text
    assert 'test@example.com' not in r.text
    assert r.json()['routing']=={'zdr':True,'data_collection':'deny'}
    assert c.get('/api/ai/settings').json()['used_today']==0
    assert c.post('/api/ai/preview',json={'message':'test'}).status_code==403


def test_invalid_daily_limit(client):
    c,h=client
    for limit in (0,-1,201):
        response=c.put('/api/ai/settings',headers=h,json={'api_key':KEY,'enabled':True,'daily_limit':limit})
        assert response.status_code==422


def test_non_zdr_error_not_silent_fallback(client,monkeypatch):
    c,h=client
    config(c,h)
    class RejectedResponse:
        status_code=400
    class RejectingClient(DummyClient):
        async def post(self,url,headers,json): return RejectedResponse()
    monkeypatch.setattr(ai.httpx,'AsyncClient',RejectingClient)
    r=c.post('/api/assistant/chat',headers=h,json={'message':'Báo cáo Ads ngày hôm nay'})
    assert r.status_code==422
    assert 'Zero Data Retention' in r.text
    assert KEY not in r.text
    assert c.get('/api/ai/settings').json()['used_today']==1