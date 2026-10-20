"""Offline OpenRouter security, tenant and read-only integration tests."""
import base64
import json
import pytest
from fastapi.testclient import TestClient

from ads_core.db import connection
from ads_core.extended import app
from ads_core.security import hash_password
from ads_core import openrouter_ai as ai

KEY = 'sk-or-v1-' + 'a' * 35


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'database.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'z' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'y' * 42)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    ai.CALLS.clear()
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       ('owner@example.com',hash_password('secure_password_999'),'tenant-a','admin'))
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       ('other@example.com',hash_password('secure_password_888'),'tenant-b','admin'))
        yield c


def login(c, email='owner@example.com', password='secure_password_999'):
    assert c.post('/api/login', json={'email':email,'password':password}).status_code == 200
    return {'X-CSRF-Token':c.get('/api/studio/me').json()['csrf']}


def test_default_off_no_external_call(client, monkeypatch):
    h=login(client)
    assert client.get('/api/ai/settings').json()['enabled'] is False
    async def forbidden(*args,**kwargs):
        raise AssertionError('External request must not happen')
    monkeypatch.setattr(ai.httpx, 'AsyncClient', forbidden)
    r=client.post('/api/assistant/chat',headers=h,json={'message':'Phân tích 7 ngày'})
    assert r.status_code == 200 and r.json()['mode']=='analyst'


def test_key_encrypted_and_never_returned(client):
    assert client.get('/api/ai/settings').status_code == 401
    h=login(client)
    assert client.put('/api/ai/settings',json={'api_key':KEY,'enabled':True}).status_code == 403
    r=client.put('/api/ai/settings',headers=h,json={'api_key':KEY,'model':'openai/gpt-4.1-mini','enabled':True})
    assert r.status_code==200, r.text
    assert r.json()['configured'] and r.json()['enabled']
    assert KEY not in r.text
    assert KEY not in client.get('/api/ai/settings').text
    with connection() as db:
        row=db.execute('SELECT token_ciphertext FROM openrouter_settings WHERE org_id=?',('tenant-a',)).fetchone()
        assert KEY not in row['token_ciphertext']
    client.post('/api/logout',headers=h)
    login(client,'other@example.com','secure_password_888')
    assert client.get('/api/ai/settings').json()['configured'] is False


def test_mocked_chat_only_sends_sanitized_aggregates(client, monkeypatch):
    h=login(client)
    key=KEY
    client.put('/api/ai/settings',headers=h,json={'api_key':key,'enabled':True,'model':'openai/gpt-4.1-mini'})
    # Other provider secrets and account labels must not reach OpenRouter.
    account=client.post('/api/accounts',headers=h,json={'platform':'demo','label':'Private Client Name','external_id':'secret-client-id','currency':'VND','token':''})
    assert account.status_code==200
    posted=[]
    class MockResponse:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':'Phân tích tối ưu dựa vào CTR.'}}],
                               'usage':{'total_tokens':19,'prompt_tokens':10,'completion_tokens':9}}
    class MockClient:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):return False
        async def post(self, url, headers, json):
            posted.append((url,headers,json))
            return MockResponse()
    monkeypatch.setattr(ai.httpx,'AsyncClient',MockClient)
    r=client.post('/api/assistant/chat',headers=h,json={'message':'Gợi ý tối ưu, sk-or-v1-abc123abc123abc123'})
    assert r.status_code==200, r.text
    assert r.json()['mode']=='openrouter'
    assert r.json()['model']=='openai/gpt-4.1-mini'
    assert len(posted)==1
    url,headers,body=posted[0]
    assert url=='https://openrouter.ai/api/v1/chat/completions'
    assert headers['Authorization']=='Bearer '+KEY
    outgoing=json.dumps(body,ensure_ascii=False)
    for sensitive in ['Private Client Name','secret-client-id','sk-or-v1-abc123abc123abc123']:
        assert sensitive not in outgoing
    assert 'demo' in outgoing and 'statistics' in outgoing
    # Key is absent from all API responses, including the chat result.
    assert KEY not in r.text


def test_revoke_then_fallback(client):
    h=login(client)
    client.put('/api/ai/settings',headers=h,json={'api_key':KEY,'enabled':True})
    r=client.delete('/api/ai/settings',headers=h)
    assert r.status_code==200
    assert not client.get('/api/ai/settings').json()['configured']
    assert client.post('/api/assistant/chat',headers=h,json={'message':'Tổng kết Ads'}).json()['mode']=='analyst'


def test_model_validation(client):
    h=login(client)
    for bad in ['http://attacker.com/key', 'evil', '../model']:
        assert client.put('/api/ai/settings',headers=h,json={'api_key':KEY,'model':bad,'enabled':True}).status_code==422
