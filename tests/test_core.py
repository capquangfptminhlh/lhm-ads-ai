"""Offline tests: isolation, browser-only auth, approval guard, source labels."""
import os,base64,pytest
from fastapi.testclient import TestClient
from ads_core.db import init_db,connection
from ads_core.security import hash_password,make_secret,hash_secret,seal,unseal
from ads_core.app import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'db.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'a'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','b'*42)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)',
                       ('test@example.com',hash_password('very_long_pass_123'),'org-A','admin'))
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)',
                       ('other@example.com',hash_password('other_long_pass_456'),'org-B','admin'))
        yield c

def logged_in(client):
    r=client.post('/api/login',json={'email':'test@example.com','password':'very_long_pass_123'})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':client.get('/api/me').json()['csrf']}

def test_unauthorized(client):
    assert client.get('/api/accounts').status_code==401
    assert client.get('/api/audit').status_code==401

def test_encryption_aad():
    import base64
    os.environ['MASTER_KEY']=base64.b64encode(b'1'*32).decode()
    ciphertext=seal('secret-value','org-A:abc')
    assert unseal(ciphertext,'org-A:abc')=='secret-value'
    with pytest.raises(Exception):unseal(ciphertext,'org-B:abc')

def test_demo_and_no_token_in_response(client):
    headers=logged_in(client)
    r=client.post('/api/accounts',headers=headers,json={'platform':'demo','label':'Demo Shop',
        'external_id':'demo-1','currency':'VND','token':''})
    assert r.status_code==200,r.text
    aid=r.json()['id']
    resp=client.get('/api/report',params={'account_id':aid})
    assert resp.status_code==200
    assert resp.json()['source']=='demo'
    assert len(resp.json()['daily'])==7
    assert 'token' not in client.get('/api/accounts').text.lower()

def test_csrf_and_separate_tenant(client):
    logged_in(client)
    assert client.post('/api/accounts',json={'platform':'demo','label':'Hi there','external_id':'xx'}).status_code==403
    with connection() as db:
        cur=db.execute('INSERT INTO accounts(org_id,platform,label,external_id) VALUES(?,?,?,?)',
                       ('org-B','demo','Not mine','other'))
        other_id=cur.lastrowid
    assert client.get('/api/report',params={'account_id':other_id}).status_code==404
    assert client.get('/api/accounts').json()==[]

def test_bearer_cannot_authenticate_or_approve(client):
    h={'Authorization':'Bearer lhm_legacy_value'}
    assert client.get('/api/accounts',headers=h).status_code==401
    assert client.get('/api/summary',headers=h).status_code==401
    assert client.post('/api/actions/1/approve',headers=h).status_code==401

def test_non_meta_returns_501(client):
    h=logged_in(client)
    r=client.post('/api/accounts',headers=h,json={'platform':'tiktok','label':'TikTok Ads','external_id':'1234567890',
             'currency':'VND','token':'test-not-a-real-access-token'})
    assert r.status_code==200
    assert client.get('/api/report',params={'account_id':r.json()['id']}).status_code==501

def test_google_requires_json_bundle(client):
    h=logged_in(client)
    r=client.post('/api/accounts',headers=h,json={'platform':'google','label':'Google Ads','external_id':'1234567890',
             'currency':'VND','token':'not-a-valid-json'})
    assert r.status_code==422

def test_meta_pause_request_requires_browser_approval(client, monkeypatch):
    import ads_core.app as mod
    h=logged_in(client)
    r=client.post('/api/accounts',headers=h,json={'platform':'meta','label':'Meta test',
        'external_id':'act_1234567890','currency':'VND','token':'placeholder_token_for_offline_test'})
    assert r.status_code==200
    aid=r.json()['id']
    result=client.post('/api/actions',headers=h,json={'account_id':aid,'campaign_id':'9876543210'})
    assert result.status_code==200
    act_id=result.json()['id']
    assert result.json()['status']=='pending'
    assert client.get('/api/actions').json()[0]['status']=='pending'
    # A wrong CSRF token is denied; this test does not send a real Meta write.
    assert client.post(f'/api/actions/{act_id}/approve',headers={'X-CSRF-Token':'incorrect'}).status_code==403
    assert client.post(f'/api/actions/{act_id}/reject',headers=h).status_code==200
    assert client.get('/api/actions').json()[0]['status']=='rejected'
    assert client.post(f'/api/actions/{act_id}/approve',headers=h).status_code==409


def test_google_read_adapter_offline_mock(client, monkeypatch):
    import asyncio
    import httpx
    from ads_core.providers import google_report
    monkeypatch.setenv('GOOGLE_ADS_DEVELOPER_TOKEN','fake_dev_token')
    token=__import__('json').dumps({'client_id':'x','client_secret':'y','refresh_token':'z'})
    acc={'id':1,'org_id':'test-org','platform':'google','external_id':'1234567890',
         'currency':'USD','token_ciphertext':seal(token,'acct:test-org:google:1234567890')}
    called=[]
    class FakeResponse:
        def __init__(self,payload):self.payload=payload
        def raise_for_status(self):pass
        def json(self):return self.payload
    class FakeClient:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return None
        async def post(self,url,**kwargs):
            called.append(url)
            if 'oauth2.googleapis.com' in url:return FakeResponse({'access_token':'temp_access_token'})
            assert kwargs['headers']['developer-token']=='fake_dev_token'
            assert 'YESTERDAY' in kwargs['json']['query']
            return FakeResponse([{'results':[{'segments':{'date':'2026-10-11'},
                'metrics':{'costMicros':'5000000','impressions':'1000','clicks':'100'}}]}])
    monkeypatch.setattr(httpx,'AsyncClient',FakeClient)
    output=asyncio.run(google_report(acc,'yesterday'))
    assert output['source']=='google_live'
    assert output['spend']==5
    assert output['clicks']==100
    assert len(called)==2
