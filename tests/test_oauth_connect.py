"""OAuth integration tests: fake provider HTTP ONLY, never real ad account data."""
import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from ads_core.db import connection
from ads_core.extended import app
from ads_core.security import hash_password, unseal, hash_secret
from ads_core import oauth_connect as oauth


@pytest.fixture
def env(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'oauth.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'k'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','e'*50)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setenv('PUBLIC_BASE_URL','http://127.0.0.1:8765')
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID','web-client-id.apps.googleusercontent.com')
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_SECRET','web-google-secret')
    monkeypatch.setenv('GOOGLE_ADS_DEVELOPER_TOKEN','fake-developer-token')
    monkeypatch.setenv('META_APP_ID','1234567890')
    monkeypatch.setenv('META_APP_SECRET','fake-meta-secret')
    with TestClient(app) as c:
        with connection() as db:
            for email,role,org in [
                ('admin@a.test','admin','org-a'),
                ('other@b.test','admin','org-b'),
                ('reader@a.test','reader','org-a'),
            ]:
                db.execute('INSERT INTO users(email,role,org_id,password_hash) VALUES (?,?,?,?)',
                           (email,role,org,hash_password('strong_password_123')))
        yield c


def login(c,email='admin@a.test'):
    resp=c.post('/api/login',json={'email':email,'password':'strong_password_123'})
    assert resp.status_code==200
    return {'X-CSRF-Token':c.get('/api/me').json()['csrf']}


def start(c,provider='google',headers=None):
    r=c.post('/api/oauth/'+provider+'/start',headers=headers)
    assert r.status_code==200,r.text
    uri=r.json()['authorization_url']
    q=parse_qs(urlparse(uri).query)
    return uri,q['state'][0],q


class Response:
    def __init__(self,payload,status_code=200):
        self.payload=payload
        self.status_code=status_code
    def raise_for_status(self):
        if self.status_code>=400:raise oauth.httpx.HTTPStatusError('Provider error',request=None,response=None)
    def json(self):return self.payload


class GoogleHTTP:
    calls=[]
    def __init__(self,*a,**kw):self.calls=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def post(self,url,**kwargs):
        self.calls.append(('post',url,kwargs))
        if 'oauth2.googleapis.com' in url:
            assert kwargs['data']['code_verifier']
            assert kwargs['data']['redirect_uri']=='http://127.0.0.1:8765/api/oauth/google/callback'
            return Response({'access_token':'google-transient-access','refresh_token':'google-refresh-token'})
        if 'googleAds:searchStream' in url:
            return Response([{'results':[{'customerClient':{'id':'9876543210',
                'descriptiveName':'Account Child','currencyCode':'USD','manager':False}}]}])
        raise AssertionError(url)
    async def get(self,url,**kwargs):
        self.calls.append(('get',url,kwargs))
        assert url.endswith('/customers:listAccessibleCustomers')
        return Response({'resourceNames':['customers/1234567890']})


class MetaHTTP:
    def __init__(self,*a,**kw):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def get(self,url,**kwargs):
        if url.endswith('/oauth/access_token'):
            if kwargs['params'].get('grant_type')=='fb_exchange_token':
                return Response({'access_token':'meta-long-lived-token'})
            return Response({'access_token':'meta-short-lived-token'})
        if url.endswith('/me/adaccounts'):
            assert kwargs['headers']['Authorization']=='Bearer meta-long-lived-token'
            return Response({'data':[{'id':'act_123456789012','name':'Agency Client','currency':'VND'}]})
        raise AssertionError(url)


def test_google_authorize_callback_select_and_import(env,monkeypatch):
    h=login(env)
    cfg=env.get('/api/oauth/status').json()
    assert cfg['google']['configured'] and cfg['meta']['configured']
    url,state,q=start(env,'google',h)
    assert url.startswith('https://accounts.google.com/')
    assert q['scope']==['https://www.googleapis.com/auth/adwords']
    assert q['code_challenge_method']==['S256']
    assert q['access_type']==['offline']
    assert q['client_id']==['web-client-id.apps.googleusercontent.com']
    assert 'web-google-secret' not in url
    monkeypatch.setattr(oauth.httpx,'AsyncClient',GoogleHTTP)
    r=env.get('/api/oauth/google/callback',params={'state':state,'code':'success'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/studio?oauth=ready'
    result=env.get('/api/oauth/pending').json()
    assert len(result)==1
    pending=result[0]
    assert {a['id'] for a in pending['accounts']}=={'1234567890','9876543210'}
    assert 'google-refresh-token' not in str(result)
    bad=env.post('/api/oauth/pending/'+pending['id']+'/import',headers=h,json={'account_ids':['9999999999']})
    assert bad.status_code==422
    r=env.post('/api/oauth/pending/'+pending['id']+'/import',headers=h,json={'account_ids':['9876543210']})
    assert r.status_code==200,r.text
    assert r.json()['imported']==1
    accounts=env.get('/api/accounts').json()
    assert len(accounts)==1 and accounts[0]['currency']=='USD' and accounts[0]['platform']=='google'
    with connection() as db:
        row=db.execute('SELECT * FROM accounts').fetchone()
        secret=json.loads(unseal(row['token_ciphertext'],'acct:org-a:google:9876543210'))
        assert secret['refresh_token']=='google-refresh-token'
        assert secret['login_customer_id']=='1234567890'
    assert env.post('/api/oauth/pending/'+pending['id']+'/import',headers=h,json={'account_ids':['9876543210']}).status_code==404
    assert env.get('/api/oauth/google/callback',params={'state':state,'code':'replay'},follow_redirects=False).status_code==400


def test_meta_authorize_and_import_no_secret_in_browser(env,monkeypatch):
    h=login(env)
    url,state,q=start(env,'meta',h)
    assert url.startswith('https://www.facebook.com/v')
    assert q['scope']==['ads_read']
    assert 'fake-meta-secret' not in url
    monkeypatch.setattr(oauth.httpx,'AsyncClient',MetaHTTP)
    r=env.get('/api/oauth/meta/callback',params={'state':state,'code':'valid'},follow_redirects=False)
    assert r.status_code==303
    pending=env.get('/api/oauth/pending').json()
    assert pending[0]['accounts'][0]['id']=='act_123456789012'
    assert 'meta-long-lived-token' not in str(pending)
    r=env.post(f'/api/oauth/pending/{pending[0]["id"]}/import',headers=h,
               json={'account_ids':['act_123456789012']})
    assert r.status_code==200
    acc=env.get('/api/accounts').json()[0]
    with connection() as db:
        cipher=db.execute('SELECT token_ciphertext FROM accounts WHERE id=?',(acc['id'],)).fetchone()[0]
    assert unseal(cipher,'acct:org-a:meta:act_123456789012')=='meta-long-lived-token'


def test_state_bound_to_session_and_tenant(env):
    h=login(env)
    _,state,_=start(env,'google',h)
    env.post('/api/logout',headers=h)
    login(env,'other@b.test')
    bad=env.get('/api/oauth/google/callback',params={'state':state,'code':'fake'},follow_redirects=False)
    assert bad.status_code==400
    assert env.get('/api/oauth/pending').json()==[]


def test_missing_credentials_returns_422_not_redirect(env,monkeypatch):
    h=login(env)
    monkeypatch.delenv('META_APP_SECRET')
    assert env.post('/api/oauth/meta/start',headers=h).status_code==422
    assert not env.get('/api/oauth/status').json()['meta']['configured']
    # Developer token sunset (2026): OAuth requires approved Google Cloud project, not legacy developer token.
    monkeypatch.delenv('GOOGLE_ADS_DEVELOPER_TOKEN')
    assert env.post('/api/oauth/google/start',headers=h).status_code==200


def test_non_admin_and_csrf_cannot_start_or_import(env):
    h=login(env)
    assert env.post('/api/oauth/google/start').status_code==403
    _,state,_=start(env,'google',h)
    assert env.get('/api/oauth/google/callback',params={'state':'invalid','code':'fake'}).status_code==400
    env.post('/api/logout',headers=h)
    reader=login(env,'reader@a.test')
    assert env.post('/api/oauth/meta/start',headers=reader).status_code==403
    assert env.get('/api/oauth/status').status_code==403


def test_public_base_origin_restrictions(env,monkeypatch):
    h=login(env)
    for base in ['https://example.com/path','https://evil.test?next=/','http://public.example.com','https://user:pass@example.com']:
        monkeypatch.setenv('PUBLIC_BASE_URL',base)
        assert env.post('/api/oauth/google/start',headers=h).status_code==503
    monkeypatch.setenv('PUBLIC_BASE_URL','https://ads.example.com')
    url,_,q=start(env,'google',h)
    assert q['redirect_uri']==['https://ads.example.com/api/oauth/google/callback']


def test_expired_state_and_pending_not_reused(env,monkeypatch):
    h=login(env)
    _,state,_=start(env,'google',h)
    with connection() as db:
        db.execute('UPDATE oauth_flows SET expires_at=? WHERE state_hash=?',(int(time.time())-1,hash_secret(state)))
    assert env.get('/api/oauth/google/callback',params={'state':state,'code':'fake'}).status_code==400


def test_same_site_lax_for_oauth_external_redirect(env):
    login(env)
    assert any(c.name=='lhm_session' and c._rest.get('SameSite','').lower()=='lax' for c in env.cookies.jar)
    routes={r.path for r in app.router.routes}
    assert '/mcp' not in routes
    assert '/api/oauth/{provider}/callback' in routes
