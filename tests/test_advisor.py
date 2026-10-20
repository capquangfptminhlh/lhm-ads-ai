"""Offline tests for unattended read-only optimization alerts."""
import base64
import time
from fastapi.testclient import TestClient
import pytest

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import advisor


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'ads.sqlite3'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'x'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','a'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setattr(advisor,'license_required',lambda:{'active':True})
    with TestClient(app) as c:
        with connection() as db:
            for email,org,role in [('admin@a.test','A','admin'),('admin@b.test','B','admin'),('reader@a.test','A','reader')]:
                db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                           (email,hash_password('secure_pass_1234'),org,role))
        yield c


def login(c,email='admin@a.test'):
    assert c.post('/api/login',json={'email':email,'password':'secure_pass_1234'}).status_code==200
    return {'X-CSRF-Token':c.get('/api/me').json()['csrf']}


def account(c,h,platform='google'):
    import json
    tok=json.dumps({'client_id':'desktop-app','client_secret':'mock-secret','refresh_token':'fake-refresh'}) if platform=='google' else 'fake_token'
    r=c.post('/api/accounts',headers=h,json={'platform':platform,'label':'Private Customer',
                 'external_id':'9876543210' if platform=='google' else 'act_1234567890',
                 'currency':'USD','token':tok})
    assert r.status_code==200,r.text
    return r.json()['id']


def campaigns():
    return [dict(id='123456789',name='Secret Account Campaign',status='ENABLED',
                 spend=200.0,clicks=130,impressions=10000,ctr_percent=0.3,
                 conversions=0,conversion_value=0)]


def test_auto_scan_deduplicates_no_ad_writes(client,monkeypatch):
    import asyncio
    h=login(client);aid=account(client,h)
    called=[]
    async def fetch(acc):
        called.append(acc['id']);return campaigns()
    monkeypatch.setattr(advisor,'list_live_campaigns',fetch)
    # Never call remote mutating logic from scanning.
    from ads_core import autopilot
    async def forbidden(*a,**kw):raise AssertionError('AD WRITE BLOCKED')
    monkeypatch.setattr(autopilot,'_apply_google',forbidden)
    with connection() as db:acc=dict(db.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone())
    a=asyncio.run(advisor.scan_account(acc,now=2000000000))
    b=asyncio.run(advisor.scan_account(acc,now=2000000300))
    c=asyncio.run(advisor.scan_account(acc,now=2000000000+86401))
    assert a['scanned'] and a['recommendations']==2
    assert not b['scanned'] and b['reason']=='already_checked'
    assert c['scanned']
    assert called==[aid,aid]
    with connection() as db:
        findings=db.execute('SELECT * FROM advisor_findings WHERE account_id=?',(aid,)).fetchall()
        assert len(findings)==2
        assert all(f['last_seen_at']==2000000000+86401 for f in findings)


def test_unavailable_provider_no_secrets_in_alerts(client,monkeypatch):
    import asyncio
    h=login(client);aid=account(client,h)
    with connection() as db:acc=dict(db.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone())
    async def broken(*a):raise RuntimeError('api secret SECRET_VALUE key')
    monkeypatch.setattr(advisor,'list_live_campaigns',broken)
    result=asyncio.run(advisor.scan_account(acc,now=2000000000))
    assert result['reason']=='provider_unavailable'
    with connection() as db:
        row=db.execute('SELECT error_code FROM advisor_scan_runs WHERE account_id=?',(aid,)).fetchone()
        assert row['error_code']=='provider_unavailable'
    assert client.get('/api/advisor/status').status_code==200
    assert 'SECRET_VALUE' not in client.get('/api/advisor/status').text


def test_agent_health_and_admin_boundaries(client,monkeypatch):
    h=login(client);aid=account(client,h)
    advisor.heartbeat(now=2000000000)
    assert advisor.agent_health(now=2000000020)['running'] is True
    assert advisor.agent_health(now=2000000500)['running'] is False
    r=client.get('/api/advisor/status');assert r.status_code==200
    assert r.json()['findings']==[]
    assert client.post(f'/api/advisor/accounts/{aid}/scan').status_code==403
    client.post('/api/logout',headers=h)
    other=login(client,'admin@b.test')
    assert client.post(f'/api/advisor/accounts/{aid}/scan',headers=other).status_code==404
    client.post('/api/logout',headers=other)
    reader=login(client,'reader@a.test')
    assert client.post(f'/api/advisor/accounts/{aid}/scan',headers=reader).status_code==403


def test_acknowledge_is_tenant_scoped_and_single_use(client,monkeypatch):
    import asyncio
    h=login(client);aid=account(client,h)
    async def fetch(acc):return campaigns()
    monkeypatch.setattr(advisor,'list_live_campaigns',fetch)
    with connection() as db:acc=dict(db.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone())
    asyncio.run(advisor.scan_account(acc,now=2000000000))
    fid=client.get('/api/advisor/status').json()['findings'][0]['id']
    assert client.post(f'/api/advisor/findings/{fid}/acknowledge').status_code==403
    client.post('/api/logout',headers=h)
    other=login(client,'admin@b.test')
    assert client.post(f'/api/advisor/findings/{fid}/acknowledge',headers=other).status_code==404
    client.post('/api/logout',headers=other)
    h=login(client)
    assert client.post(f'/api/advisor/findings/{fid}/acknowledge',headers=h).status_code==200
    assert client.post(f'/api/advisor/findings/{fid}/acknowledge',headers=h).status_code==404
    assert next(x for x in client.get('/api/advisor/status').json()['findings'] if x['id']==fid)['acknowledged_at']