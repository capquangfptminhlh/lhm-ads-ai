"""Permission checks are read-only, tenant scoped and never reveal secrets."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import permissions


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'permissions.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'p'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','s'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as c:
        with connection() as db:
            for email,org,role in [('owner@a.test','A','admin'),('other@b.test','B','admin'),
                                   ('reader@a.test','A','reader')]:
                db.execute('INSERT INTO users(email,org_id,role,password_hash) VALUES(?,?,?,?)',
                           (email,org,role,hash_password('a_strong_password_123')))
        yield c

def login(c,email='owner@a.test'):
    assert c.post('/api/login',json={'email':email,'password':'a_strong_password_123'}).status_code==200
    return {'X-CSRF-Token':c.get('/api/me').json()['csrf']}

def account(c,h,platform):
    token='fake_valid_meta_access_token_123456' if platform=='meta' else json.dumps({
        'client_id':'google-client','client_secret':'google-secret','refresh_token':'refresh-private',
        'login_customer_id':'1234567890'})
    r=c.post('/api/accounts',headers=h,json={'platform':platform,'label':'Private Client',
        'external_id':'act_1234567890' if platform=='meta' else '9876543210','token':token})
    assert r.status_code==200,r.text
    return r.json()['id'],token

class Res:
    def __init__(self,code=200,body=None):self.status_code=code;self.body=body if body is not None else {}
    def json(self):return self.body

class MetaMock:
    def __init__(self,*a,**kw):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*a):return False
    async def post(self,*a,**k):raise AssertionError('A Meta write was attempted')
    async def get(self,url,**kw):
        if url.endswith('/me/permissions'):return Res(body={'data':[
            {'permission':'ads_read','status':'granted'},
            {'permission':'ads_management','status':'granted'},
            {'permission':'business_management','status':'declined'}]})
        if url.endswith('/act_1234567890') or url.endswith('/act_1234567890/insights'):
            return Res(body={'data':[]})
        raise AssertionError(url)

class GoogleMock:
    def __init__(self,*a,**kw):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*a):return False
    async def get(self,*a,**kw):raise AssertionError('unexpected Google request')
    async def post(self,url,**kw):
        if url.endswith('/token'):
            return Res(body={'access_token':'PRIVATE_GOOGLE_ACCESS_TOKEN',
                             'scope':'https://www.googleapis.com/auth/adwords'})
        assert url.endswith('/googleAds:searchStream')
        assert kw['headers']['login-customer-id']=='1234567890'
        return Res(body=[{'results':[]}])


def test_meta_scopes_not_mutation_rights(client,monkeypatch):
    h=login(client);aid,token=account(client,h,'meta')
    monkeypatch.setattr(permissions.httpx,'AsyncClient',MetaMock)
    r=client.post(f'/api/permissions/probe/{aid}',headers=h)
    assert r.status_code==200,r.text
    d=r.json()
    assert d['token']['status']=='confirmed' and d['report_read']['status']=='confirmed'
    assert d['scope_manage']['status']=='confirmed'
    assert all(d[k]['status']=='unverified' for k in permissions.WRITES)
    assert token not in r.text and 'Private Client' not in r.text
    assert 'business_management' not in d['granted_scopes']

def test_google_scope_not_mutation_rights(client,monkeypatch):
    h=login(client);aid,token=account(client,h,'google')
    monkeypatch.setattr(permissions.httpx,'AsyncClient',GoogleMock)
    r=client.post(f'/api/permissions/probe/{aid}',headers=h)
    assert r.status_code==200,r.text
    d=r.json()
    assert d['account_read']['status']=='confirmed' and d['report_read']['status']=='confirmed'
    assert d['scope_manage']['status']=='confirmed'
    assert all(d[k]['status']=='unverified' for k in permissions.WRITES)
    assert token not in r.text and 'PRIVATE_GOOGLE_ACCESS_TOKEN' not in r.text

def test_auth_and_tenant_isolation(client):
    assert client.post('/api/permissions/probe/1').status_code==401
    h=login(client);aid,_=account(client,h,'meta')
    assert client.post(f'/api/permissions/probe/{aid}').status_code==403
    client.post('/api/logout',headers=h)
    other=login(client,'other@b.test')
    assert client.post(f'/api/permissions/probe/{aid}',headers=other).status_code==404
    client.post('/api/logout',headers=other)
    reader=login(client,'reader@a.test')
    assert client.post(f'/api/permissions/probe/{aid}',headers=reader).status_code==403

def test_no_probe_demo(client):
    h=login(client)
    r=client.post('/api/accounts',headers=h,json={'platform':'demo','label':'Demo Account',
        'external_id':'demo-123','token':''})
    assert r.status_code==200
    assert client.post(f'/api/permissions/probe/{r.json()["id"]}',headers=h).status_code==422
    assert client.get('/mcp').status_code==404
