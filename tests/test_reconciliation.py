"""Read-only post-write confirmation tests. Never call live Ads provider mutation APIs."""
import asyncio
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import autopilot as ap
from ads_core import reconciliation as rec
from ads_core.monitoring import init_monitor_db


@pytest.fixture
def sandbox(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'app.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'X'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','k'*45)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setattr(ap,'license_required',lambda: {'active':True})
    with TestClient(app) as c:
        with connection() as db:
            for email,role,org in (
                ('admin@a.test','admin','tenant-a'),
                ('viewer@a.test','reader','tenant-a'),
                ('admin@b.test','admin','tenant-b'),
            ):
                db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                           (email,hash_password('very_good_password_123'),org,role))
        yield c


def login(c,email='admin@a.test'):
    assert c.post('/api/login',json={'email':email,'password':'very_good_password_123'}).status_code==200
    return {'X-CSRF-Token':c.get('/api/me').json()['csrf']}


class DummyHTTP:
    def __init__(self,*a,**kw):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def post(self,*args,**kw):raise AssertionError('Provider write is forbidden in verification!')
    async def get(self,*args,**kw):raise AssertionError('Snapshot mocked: no real HTTP')


def setup_plan(c,monkeypatch):
    h=login(c)
    account=c.post('/api/accounts',headers=h,json={
        'platform':'meta','label':'Authorized customer','external_id':'act_1234567890',
        'currency':'USD','token':'test_meta_token'}).json()['id']
    policy=c.put(f'/api/autopilot/accounts/{account}/policy',headers=h,json={
        'writes_enabled':True,'emergency_stop':False,'max_change_percent':10,'max_changes_per_day':2})
    assert policy.status_code==200,policy.text
    async def old_snapshot(*args):
        return 1000,'https://graph.facebook.com/v24.0',{}
    monkeypatch.setattr(ap,'_snapshot',old_snapshot)
    monkeypatch.setattr(rec.httpx,'AsyncClient',DummyHTTP)
    created=c.post('/api/autopilot/plans',headers=h,json={
        'account_id':account,'action_type':'adset_daily_budget',
        'target_id':'1234567','new_value':1100})
    assert created.status_code==200,created.text
    pid=created.json()['id']
    with connection() as db:
        db.execute("UPDATE autopilot_plans SET status='accepted_unverified' WHERE id=?",(pid,))
    return h,account,pid


def test_verify_read_only_confirms_changed_value(sandbox,monkeypatch):
    h,aid,pid=setup_plan(sandbox,monkeypatch)
    async def new_snapshot(*args):
        return 1100,'https://graph.facebook.com/v24.0',{}
    monkeypatch.setattr(ap,'_snapshot',new_snapshot)
    assert sandbox.post(f'/api/autopilot/plans/{pid}/verify').status_code==403
    answer=sandbox.post(f'/api/autopilot/plans/{pid}/verify',headers=h)
    assert answer.status_code==200,answer.text
    value=answer.json()
    assert (value['status'],value['outcome'],value['verified_value'],value['read_only'])==(
        'completed','verified_new',1100,True)
    last=sandbox.get('/api/autopilot/plans').json()[0]
    assert last['status']=='completed' and last['verify_attempts']==1
    assert last['last_verified_at'] is not None
    assert sandbox.post(f'/api/autopilot/plans/{pid}/verify',headers=h).status_code==409


def test_stale_and_unexpected_are_not_retried(sandbox,monkeypatch):
    h,aid,pid=setup_plan(sandbox,monkeypatch)
    async def old(*args):return 1000,'https://graph.facebook.com/v24.0',{}
    monkeypatch.setattr(ap,'_snapshot',old)
    one=sandbox.post(f'/api/autopilot/plans/{pid}/verify',headers=h).json()
    assert one['outcome']=='still_old' and one['status']=='accepted_unverified'
    async def different(*args):return 1050,'https://graph.facebook.com/v24.0',{}
    monkeypatch.setattr(ap,'_snapshot',different)
    two=sandbox.post(f'/api/autopilot/plans/{pid}/verify',headers=h).json()
    assert two['status']=='needs_review' and two['outcome']=='unexpected_value'
    assert sandbox.get('/api/autopilot/plans').json()[0]['verify_attempts']==2


def test_provider_failure_redacted_and_cannot_touch_other_tenant(sandbox,monkeypatch):
    h,aid,pid=setup_plan(sandbox,monkeypatch)
    async def crash(*args):raise ValueError('SECRET_TOKEN=must_not_appear')
    monkeypatch.setattr(ap,'_snapshot',crash)
    result=sandbox.post(f'/api/autopilot/plans/{pid}/verify',headers=h)
    assert result.status_code==200
    assert result.json()['outcome']=='api_unavailable'
    assert 'must_not_appear' not in result.text
    assert 'must_not_appear' not in sandbox.get('/api/autopilot/plans').text
    sandbox.post('/api/logout',headers=h)
    reader=login(sandbox,'viewer@a.test')
    assert sandbox.post(f'/api/autopilot/plans/{pid}/verify',headers=reader).status_code==403
    sandbox.post('/api/logout',headers=reader)
    other=login(sandbox,'admin@b.test')
    assert sandbox.post(f'/api/autopilot/plans/{pid}/verify',headers=other).status_code==404
    assert sandbox.get('/api/autopilot/plans').json()==[]


def test_background_scans_only_opted_in_org_and_throttles(sandbox,monkeypatch):
    h,aid,pid=setup_plan(sandbox,monkeypatch)
    async def changed(*args):return 1100,'https://graph.facebook.com/v24.0',{}
    monkeypatch.setattr(ap,'_snapshot',changed)
    init_monitor_db()
    assert asyncio.run(rec.reconcile_due({'tenant-a'}))['checked']==0
    with connection() as db:
        db.execute('INSERT INTO monitor_settings(org_id,enabled,poll_minutes) VALUES (?,?,?)',
                   ('tenant-a',1,15))
    assert asyncio.run(rec.reconcile_due({'tenant-b'}))['checked']==0
    assert asyncio.run(rec.reconcile_due({'tenant-a'}))['checked']==1
    assert sandbox.get('/api/autopilot/plans').json()[0]['status']=='completed'
    assert asyncio.run(rec.reconcile_due({'tenant-a'}))['checked']==0


def test_background_does_not_poll_more_than_limit(sandbox,monkeypatch):
    h,aid,pid=setup_plan(sandbox,monkeypatch)
    init_monitor_db()
    with connection() as db:
        db.execute('INSERT INTO monitor_settings(org_id,enabled,poll_minutes) VALUES (?,?,?)',
                   ('tenant-a',1,15))
        db.execute('UPDATE autopilot_plans SET verify_attempts=? WHERE id=?',
                   (rec.MAX_AUTO_ATTEMPTS,pid))
    async def never(*args):
        raise AssertionError('No extra query should occur when exhausted')
    monkeypatch.setattr(ap,'_snapshot',never)
    assert asyncio.run(rec.reconcile_due({'tenant-a'}))['checked']==0
