"""Never send real Ads writes. All API data and license are mocked."""
import base64
import json
import time
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import autopilot as ap

@pytest.fixture
def env(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'app.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'q'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','s'*45)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setattr(ap,'license_required',lambda: {'active':True})
    with TestClient(app) as client:
        with connection() as db:
            db.execute('INSERT INTO users(email,role,org_id,password_hash) VALUES(?,?,?,?)',
                       ('admin@a.test','admin','org-a',hash_password('strong_password_123')))
            db.execute('INSERT INTO users(email,role,org_id,password_hash) VALUES(?,?,?,?)',
                       ('other@b.test','admin','org-b',hash_password('strong_password_123')))
            db.execute('INSERT INTO users(email,role,org_id,password_hash) VALUES(?,?,?,?)',
                       ('viewer@a.test','reader','org-a',hash_password('strong_password_123')))
        yield client

def login(c,email='admin@a.test'):
    assert c.post('/api/login',json={'email':email,'password':'strong_password_123'}).status_code==200
    return {'X-CSRF-Token':c.get('/api/me').json()['csrf']}

def account(c,h,platform):
    tok='mock_meta_token_xyz' if platform=='meta' else json.dumps({'client_id':'google','client_secret':'secret','refresh_token':'refresh'})
    r=c.post('/api/accounts',headers=h,json={'platform':platform,'label':'Client-Private',
                 'external_id':'act_1234567890' if platform=='meta' else '9876543210',
                 'currency':'USD','token':tok})
    assert r.status_code==200,r.text
    return r.json()['id']

def enable(c,h,aid):
    p='/api/autopilot/accounts/'+str(aid)+'/policy'
    assert c.put(p,headers=h,json={'writes_enabled':True,'emergency_stop':True}).status_code==422
    r=c.put(p,headers=h,json={'writes_enabled':True,'emergency_stop':False,
                              'max_change_percent':10,'max_changes_per_day':2})
    assert r.status_code==200,r.text

class NoHTTP:
    def __init__(self,*a,**k):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*a):return False
    async def post(self,*a,**k):raise AssertionError('Unexpected external request')
    async def get(self,*a,**k):raise AssertionError('Unexpected external request')

async def snapshot(acc,kind,target,c):
    return 1000000,'https://googleads.googleapis.com/v25/customers/9876543210',{'Authorization':'Bearer MOCK'}

def test_policy_fail_closed_and_csrf(env,monkeypatch):
    monkeypatch.setattr(ap.httpx,'AsyncClient',NoHTTP)
    h=login(env)
    aid=account(env,h,'google')
    p=f'/api/autopilot/accounts/{aid}/policy'
    assert env.get(p).json()['emergency_stop'] is True
    assert env.put(p,json={'writes_enabled':True,'emergency_stop':False}).status_code==403
    assert env.post('/api/autopilot/plans',headers=h,json={'account_id':aid,'action_type':'daily_budget',
                'target_id':'1234567','new_value':1100000}).status_code==403
    enable(env,h,aid)
    assert env.get(p).json()['writes_enabled'] is True
    assert env.post('/api/autopilot/emergency-stop').status_code==403
    assert env.post('/api/autopilot/emergency-stop',headers=h).json()['mode']=='monitor_only'
    assert env.get(p).json()['emergency_stop'] is True


def test_plan_review_and_verify_once(env,monkeypatch):
    h=login(env);aid=account(env,h,'google');enable(env,h,aid)
    monkeypatch.setattr(ap.httpx,'AsyncClient',NoHTTP)
    monkeypatch.setattr(ap,'_snapshot',snapshot)
    calls=[]
    async def apply(*args):calls.append(args[1]);return True
    monkeypatch.setattr(ap,'_apply_google',apply)
    route='/api/autopilot/plans'
    req={'account_id':aid,'action_type':'daily_budget','target_id':'1234567','new_value':1100000}
    assert env.post(route,json=req).status_code==403
    assert env.post(route,headers=h,json={**req,'new_value':1500000}).status_code==422
    made=env.post(route,headers=h,json=req);assert made.status_code==200,made.text
    pid=made.json()['id'];assert made.json()['old_value']==1000000
    assert env.post(f'{route}/{pid}/approve').status_code==403
    r=env.post(f'{route}/{pid}/approve',headers=h)
    assert r.status_code==200,r.text
    assert r.json()['status']=='accepted_unverified'
    assert calls==['daily_budget']
    assert env.post(f'{route}/{pid}/approve',headers=h).status_code==409
    assert env.get(route).json()[0]['provider_result'].startswith('API tiếp nhận')
    assert env.post(route,headers=h,json=req).status_code==429


def test_stale_value_and_disabled_policy_block_write(env,monkeypatch):
    h=login(env);aid=account(env,h,'meta');enable(env,h,aid)
    monkeypatch.setattr(ap.httpx,'AsyncClient',NoHTTP)
    monkeypatch.setattr(ap,'_snapshot',snapshot)
    req={'account_id':aid,'action_type':'adset_daily_budget','target_id':'1234567','new_value':950000}
    r=env.post('/api/autopilot/plans',headers=h,json=req)
    assert r.status_code==200,r.text;pid=r.json()['id']
    async def changed(*args):return (1000001,'https://graph.facebook.com/v24.0',{})
    monkeypatch.setattr(ap,'_snapshot',changed)
    async def never(*a,**kw):raise AssertionError('WRITE!')
    monkeypatch.setattr(ap,'_apply_meta',never)
    r=env.post(f'/api/autopilot/plans/{pid}/approve',headers=h)
    assert r.status_code==409
    assert env.get('/api/autopilot/plans').json()[0]['status']=='rejected_stale'
    # Another pending plan blocked by global stop without writes.
    monkeypatch.setattr(ap,'_snapshot',snapshot)
    pid2=env.post('/api/autopilot/plans',headers=h,json=req).json()['id']
    env.post('/api/autopilot/emergency-stop',headers=h)
    assert env.post(f'/api/autopilot/plans/{pid2}/approve',headers=h).status_code==403


def test_cross_tenant_and_reader(env,monkeypatch):
    h=login(env);aid=account(env,h,'google')
    env.post('/api/logout',headers=h)
    other=login(env,'other@b.test')
    assert env.get(f'/api/autopilot/accounts/{aid}/policy').status_code==404
    assert env.put(f'/api/autopilot/accounts/{aid}/policy',headers=other,
                   json={'writes_enabled':True,'emergency_stop':False}).status_code==404
    env.post('/api/logout',headers=other)
    reader=login(env,'viewer@a.test')
    assert env.get(f'/api/autopilot/accounts/{aid}/policy').status_code==200
    assert env.put(f'/api/autopilot/accounts/{aid}/policy',headers=reader,
                   json={'writes_enabled':True,'emergency_stop':False}).status_code==403
    assert env.post('/api/autopilot/plans',headers=reader,json={'account_id':aid,'action_type':'daily_budget',
                   'target_id':'1234567','new_value':1050000}).status_code==403


def test_google_shared_budget_and_smart_bidding_rejected(monkeypatch):
    from ads_core import autopilot
    class Mock:
        async def post(self,url,**kw):
            class R:
                status_code=200
                def json(self):return [{'results':[{'campaignBudget':{'id':'1234567','amountMicros':'1000000','explicitlyShared':True}}]}]
            return R()
    async def acc(*a):return '9876543210','v25',{}
    monkeypatch.setattr(autopilot,'google_access',acc)
    import asyncio
    with pytest.raises(HTTPException) as ex:
        asyncio.run(autopilot._google_read({'platform':'google'},'daily_budget','1234567',Mock()))
    assert ex.value.status_code==422


def test_google_validation_before_write_and_resource_name():
    class HTTP:
        def __init__(self):self.log=[]
        async def post(self,url,**kw):
            self.log.append((url,kw['json']))
            class R:
                status_code=200
                def json(self):return {'results':[{'resourceName':'customers/9876543210/campaignBudgets/1234567'}]}
            return R()
    import asyncio
    c=HTTP()
    assert asyncio.run(ap._apply_google({'platform':'google'},'daily_budget','1234567',1100000,
                   'https://googleads.googleapis.com/v25/customers/9876543210',{},c)) is True
    assert len(c.log)==2
    assert c.log[0][1]['validateOnly'] is True and c.log[1][1]['validateOnly'] is False
    assert c.log[0][1]['operations'][0]['update']['resourceName']=='customers/9876543210/campaignBudgets/1234567'


def test_plan_expiration_before_real_mutation(env,monkeypatch):
    h=login(env);aid=account(env,h,'google');enable(env,h,aid)
    monkeypatch.setattr(ap.httpx,'AsyncClient',NoHTTP);monkeypatch.setattr(ap,'_snapshot',snapshot)
    plan=env.post('/api/autopilot/plans',headers=h,json={'account_id':aid,'action_type':'daily_budget','target_id':'1234567','new_value':900000})
    assert plan.status_code==200;pid=plan.json()['id']
    with connection() as db:db.execute('UPDATE autopilot_plans SET created_at=? WHERE id=?',(int(time.time())-999,pid))
    assert env.post(f'/api/autopilot/plans/{pid}/approve',headers=h).status_code==409
    assert env.get('/api/autopilot/plans').json()[0]['status']=='pending'