"""Per-account KPI objectives: safe deterministic alerts, permissions, and recovery."""
import asyncio
import base64
import json
from fastapi.testclient import TestClient
import pytest
from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import advisor,goals

@pytest.fixture
def context(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'goals.sqlite3'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'Y'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','q'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setattr(advisor,'license_required',lambda: {'active':True})
    with TestClient(app) as client:
        with connection() as db:
            for email,org,role in [('admin@a.test','a','admin'),('admin@b.test','b','admin'),('reader@a.test','a','reader')]:
                db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                           (email,hash_password('strong_password_123'),org,role))
        yield client

def login(c,email='admin@a.test'):
    assert c.post('/api/login',json={'email':email,'password':'strong_password_123'}).status_code==200
    return {'X-CSRF-Token':c.get('/api/me').json()['csrf']}

def account(c,h,platform='google'):
    token=json.dumps({'client_id':'oauth','client_secret':'mock_local_client_secret','refresh_token':'fake_refresh'}) if platform=='google' else 'fake_meta_token'
    r=c.post('/api/accounts',headers=h,json={
        'platform':platform,'label':'Business','external_id':'9876543210' if platform=='google' else 'act_1234567890',
        'currency':'VND','token':token})
    assert r.status_code==200,r.text
    return r.json()['id']

def goal_payload(**changes):
    return dict(enabled=True,objective='cpa',target=20000,min_conversions=5,min_clicks=100,**changes)

def campaign(spend=210000,conversions=6):
    return {'id':'123456789','status':'ENABLED','name':'Private Campaign','clicks':200,
            'impressions':10000,'ctr_percent':2.0,'spend':spend,'conversions':conversions,
            'cpa':round(spend/conversions,2),'roas':2.1}

def test_goal_validation_and_permissions(context):
    c=context;h=login(c);aid=account(c,h)
    route=f'/api/goals/accounts/{aid}'
    assert c.get(route).json()['goal'] is None
    assert c.put(route,json=goal_payload()).status_code==403
    assert c.put(route,headers=h,json={**goal_payload(),'target':0}).status_code==422
    assert c.put(route,headers=h,json={**goal_payload(),'objective':'roas','target':1500}).status_code==422
    r=c.put(route,headers=h,json=goal_payload())
    assert r.status_code==200,r.text
    assert r.json()['goal']['target']==20000
    assert r.json()['goal']['currency']=='VND'
    c.post('/api/logout',headers=h)
    reader=login(c,'reader@a.test')
    assert c.get(route).status_code==200
    assert c.put(route,headers=reader,json=goal_payload()).status_code==403
    c.post('/api/logout',headers=reader)
    other=login(c,'admin@b.test')
    assert c.get(route).status_code==404
    assert c.put(route,headers=other,json=goal_payload()).status_code==404

def test_google_metrics_require_adequate_data():
    goal={'enabled':1,'objective':'cpa','target':20000,'min_conversions':5,'min_clicks':100,'currency':'VND'}
    x=goals.evaluate_goals([campaign()], 'google','VND',goal)
    assert len(x)==1 and x[0]['code']=='cpa_above_goal' and x[0]['level']=='high'
    assert goals.evaluate_goals([campaign(conversions=2)],'google','VND',goal)==[]
    assert goals.evaluate_goals([campaign()],'meta','VND',goal)==[]
    assert goals.evaluate_goals([campaign()],'google','USD',goal)==[]
    assert goals.evaluate_goals([{**campaign(),'cpa':None}],'google','VND',goal)==[]
    assert goals.evaluate_goals([{**campaign(),'clicks':None}],'google','VND',goal)==[]
    goal['objective']='roas';goal['target']=3.0
    r=goals.evaluate_goals([campaign()],'google','VND',goal)
    assert len(r)==1 and r[0]['code']=='roas_below_goal'
    assert goals.evaluate_goals([{**campaign(),'roas':None}],'google','VND',goal)==[]

def test_meta_goal_cannot_be_enabled(context):
    c=context;h=login(c);aid=account(c,h,'meta')
    route=f'/api/goals/accounts/{aid}'
    assert c.put(route,headers=h,json=goal_payload()).status_code==422
    r=c.put(route,headers=h,json={**goal_payload(),'enabled':False})
    assert r.status_code==200,r.text
    assert r.json()['evaluation_supported'] is False

def test_scan_tracks_goal_recovers_and_reappears(context,monkeypatch):
    c=context;h=login(c);aid=account(c,h)
    r=c.put(f'/api/goals/accounts/{aid}',headers=h,json=goal_payload())
    assert r.status_code==200,r.text
    with connection() as db:
        acc=dict(db.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone())
    output=[campaign()]
    async def read_campaigns(acc):return output
    monkeypatch.setattr(advisor,'list_live_campaigns',read_campaigns)
    first=asyncio.run(advisor.scan_account(acc,now=2000000000))
    assert first['recommendations']==1
    status=c.get('/api/advisor/status').json()
    warning=status['findings'][0]
    assert warning['rule_code']=='cpa_above_goal' and warning['severity']=='high'
    assert warning['resolved_at'] is None
    assert c.post('/api/advisor/findings/'+str(warning['id'])+'/acknowledge',headers=h).status_code==200
    output[:]=[campaign(spend=90000)]
    second=asyncio.run(advisor.scan_account(acc,now=2000000000+86401))
    assert second['scanned']
    recovered=c.get('/api/advisor/status').json()['findings'][0]
    assert recovered['resolved_at'] is not None
    output[:]=[campaign()]
    third=asyncio.run(advisor.scan_account(acc,now=2000000000+86401*2))
    assert third['recommendations']==1
    again=c.get('/api/advisor/status').json()['findings'][0]
    assert again['id']==warning['id'] and again['resolved_at'] is None
    assert again['acknowledged_at'] is None

def test_partial_campaign_scan_keeps_unseen_findings(context,monkeypatch):
    c=context;h=login(c);aid=account(c,h)
    assert c.put(f'/api/goals/accounts/{aid}',headers=h,json=goal_payload()).status_code==200
    with connection() as db:
        acc=dict(db.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone())
    results=[campaign()]
    async def reader(acc):return results
    monkeypatch.setattr(advisor,'list_live_campaigns',reader)
    asyncio.run(advisor.scan_account(acc,now=2000000000))
    results[:]=[{**campaign(spend=90000),'id':'987654321'}]
    asyncio.run(advisor.scan_account(acc,now=2000000000+86401))
    existing=c.get('/api/advisor/status').json()['findings']
    previous=next(x for x in existing if x['campaign_id']=='123456789')
    assert previous['resolved_at'] is None
