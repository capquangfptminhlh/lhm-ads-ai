"""Offline fake Ads API: no external writes or customer access. """
import base64
import json

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import google_mutations,optimizations, licensing


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'ads.db'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'p'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','k'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as c:
        with connection() as db:
            for email,org,role in [('admin@a.test','tenant_a','admin'),('other@b.test','tenant_b','admin'),
                                   ('reader@a.test','tenant_a','reader')]:
                db.execute('INSERT INTO users(email,org_id,role,password_hash) VALUES (?,?,?,?)',
                           (email,org,role,hash_password('a_strong_password_123')))
        yield c


def login(c,email='admin@a.test'):
    assert c.post('/api/login',json={'email':email,'password':'a_strong_password_123'}).status_code==200
    return {'X-CSRF-Token':c.get('/api/me').json()['csrf']}


def account(c,h,platform):
    token=json.dumps({'client_id':'desktop-google.apps.googleusercontent.com','refresh_token':'private-refresh','client_secret':'private-client-secret',
                      'login_customer_id':'1234567890'}) if platform=='google' else 'private-meta-token'
    external='9876543210' if platform=='google' else 'act_123456789012'
    r=c.post('/api/accounts',headers=h,json={'label':'Private Client','platform':platform,'external_id':external,
                                             'currency':'VND','token':token})
    assert r.status_code==200,r.text
    return r.json()['id']


class Response:
    def __init__(self,body,code=200):self.body=body;self.status_code=code
    def json(self):return self.body
    def raise_for_status(self):
        if self.status_code>=400:raise HTTPException(self.status_code,'Mock Ads API status')


class GoogleClient:
    calls=[]
    campaign_status='ENABLED'
    def __init__(self,*args,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def get(self,*args,**kwargs):raise AssertionError('Unexpected GET')
    async def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if url=='https://oauth2.googleapis.com/token':
            assert kwargs['data']['refresh_token']=='private-refresh'
            return Response({'access_token':'transient'})
        if url.endswith('/googleAds:searchStream'):
            query=kwargs['json']['query']
            if 'campaign.id =' in query:
                return Response([{'results':[{'campaign':{'id':'12345678901','status':self.campaign_status}}]}])
            return Response([{'results':[{'campaign':{'id':'12345678901','name':'Google Search Campaign','status':'ENABLED'},
                                         'metrics':{'costMicros':'250000000','clicks':'120','impressions':'60000','conversions':0,
                                                    'conversionsValue':0}}]}])
        if url.endswith('/campaigns:mutate'):
            assert len(kwargs['json']['operations'])==1
            op=kwargs['json']['operations'][0]
            assert op['updateMask']=='status'
            assert op['update']=={'resourceName':'customers/9876543210/campaigns/12345678901','status':'PAUSED'}
            return Response({'results':[{'resourceName':'customers/9876543210/campaigns/12345678901'}]})
        raise AssertionError('Unexpected external HTTP: '+url)


class MetaClient:
    calls=[]
    def __init__(self,*a,**kw):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*a):return False
    async def post(self,*a,**kw):raise AssertionError('No Meta write from insight route')
    async def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if url.endswith('/campaigns'):
            return Response({'data':[{'id':'12345678901','name':'Meta Campaign','status':'ACTIVE','effective_status':'ACTIVE'}]})
        if url.endswith('/adsets'):
            return Response({'data':[]})
        if url.endswith('/insights'):
            return Response({'data':[{'campaign_id':'12345678901','spend':'190000','clicks':'150','impressions':'100000'}]})
        raise AssertionError(url)


def test_google_campaign_metrics_and_heuristics(client,monkeypatch):
    h=login(client);aid=account(client,h,'google')
    GoogleClient.calls=[]
    monkeypatch.setattr(optimizations.httpx,'AsyncClient',GoogleClient)
    r=client.get(f'/api/optimizations/accounts/{aid}')
    assert r.status_code==200,r.text
    d=r.json();assert d['platform']=='google' and len(d['campaigns'])==1
    c=d['campaigns'][0];assert c['spend']==250 and c['clicks']==120 and c['conversions']==0
    assert c['roas']==0 and c['cpa'] is None
    assert {x['code'] for x in d['recommendations']}=={'low_ctr','no_reported_conversions'}
    assert all(not u.endswith('campaigns:mutate') for u,_ in GoogleClient.calls)
    assert 'private-refresh' not in r.text


def test_meta_missing_conversions_not_fake(client,monkeypatch):
    h=login(client);aid=account(client,h,'meta')
    MetaClient.calls=[]
    monkeypatch.setattr(optimizations.httpx,'AsyncClient',MetaClient)
    r=client.get(f'/api/optimizations/accounts/{aid}')
    assert r.status_code==200
    c=r.json()['campaigns'][0]
    assert c['spend']==190000 and c['cpa'] is None and c['roas'] is None and c['conversions'] is None
    assert all(u.startswith('https://graph.facebook.com/') for u,_ in MetaClient.calls)


def test_insights_private_and_tenant_scoped(client):
    assert client.get('/api/optimizations/accounts/1').status_code==401
    h=login(client);aid=account(client,h,'google')
    client.post('/api/logout',headers=h)
    login(client,'other@b.test')
    assert client.get(f'/api/optimizations/accounts/{aid}').status_code==404


def test_google_pause_requires_admin_and_validates_first(client,monkeypatch):
    h=login(client);aid=account(client,h,'google')
    r=client.post('/api/actions',headers=h,json={'account_id':aid,'campaign_id':'12345678901'})
    assert r.status_code==200,r.text
    action=r.json()['id']
    assert client.post(f'/api/actions/{action}/approve').status_code==403
    monkeypatch.setattr(licensing,'license_required',lambda:{'active':True})
    GoogleClient.calls=[]
    monkeypatch.setattr(google_mutations.httpx,'AsyncClient',GoogleClient)
    r=client.post(f'/api/actions/{action}/approve',headers=h)
    assert r.status_code==200,r.text
    urls=[(url,kw) for url,kw in GoogleClient.calls if url.endswith('/campaigns:mutate')]
    assert len(urls)==2
    assert urls[0][1]['json']['validateOnly'] is True
    assert urls[1][1]['json']['validateOnly'] is False
    assert client.post(f'/api/actions/{action}/approve',headers=h).status_code==409
    assert client.get('/api/actions').json()[0]['status']=='completed'


def test_google_pause_fails_closed_when_wrong_status(client,monkeypatch):
    h=login(client);aid=account(client,h,'google')
    r=client.post('/api/actions',headers=h,json={'account_id':aid,'campaign_id':'12345678901'})
    monkeypatch.setattr(licensing,'license_required',lambda:{'active':True})
    class NotEnabled(GoogleClient):campaign_status='PAUSED'
    NotEnabled.calls=[]
    monkeypatch.setattr(google_mutations.httpx,'AsyncClient',NotEnabled)
    resp=client.post(f'/api/actions/{r.json()["id"]}/approve',headers=h)
    assert resp.status_code==409
    assert not any(url.endswith('/campaigns:mutate') for url,_ in NotEnabled.calls)
    assert client.get('/api/actions').json()[0]['status']=='failed'


def test_write_is_never_exposed_to_reader(client):
    h=login(client);aid=account(client,h,'google')
    client.post('/api/logout',headers=h)
    reader=login(client,'reader@a.test')
    assert client.post('/api/actions',headers=reader,json={'account_id':aid,'campaign_id':'12345678901'}).status_code==403
    assert client.get('/mcp').status_code==404
