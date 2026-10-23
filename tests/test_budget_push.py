"""Budget alerts: tenant scoping, daily idempotency, no fake spend, Push SSRF guards."""
import asyncio
import base64
from datetime import date
import pytest
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import budget_push

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'push.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'x'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','s'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(org_id,email,role,password_hash) VALUES(?,?,?,?)',
              ('orgA','owner-push@example.com','admin',hash_password('long-password-999')))
            db.execute('INSERT INTO accounts(org_id,platform,label,external_id,currency,token_ciphertext) VALUES(?,?,?,?,?,?)',
              ('orgA','google','Account A','1111111111','VND','not-a-real-token'))
            db.execute('INSERT INTO accounts(org_id,platform,label,external_id,currency,token_ciphertext) VALUES(?,?,?,?,?,?)',
              ('orgB','google','Account B','2222222222','VND','not-a-real-token'))
        assert c.post('/api/login',json={'email':'owner-push@example.com','password':'long-password-999'}).status_code==200
        csrf=c.get('/api/studio/me').json()['csrf']
        yield c,{'x-csrf-token':csrf}

def test_budget_settings_and_tenant_guard(client):
    c,h=client
    rows=c.get('/api/budgets').json()['rules']
    assert len(rows)==1 and rows[0]['label']=='Account A'
    assert c.put('/api/budgets/1',json={'threshold':200000}).status_code==403
    assert c.put('/api/budgets/2',headers=h,json={'threshold':200000}).status_code==404
    r=c.put('/api/budgets/1',headers=h,json={'threshold':200000})
    assert r.status_code==200 and r.json()['currency']=='VND'
    assert c.put('/api/budgets/1',headers=h,json={'threshold':-1}).status_code==422
    assert c.get('/api/budgets').json()['rules'][0]['threshold']==200000

def test_budget_alert_only_once_per_day_and_real_api(client,monkeypatch):
    c,h=client
    c.put('/api/budgets/1',headers=h,json={'threshold':200000})
    collected=[]
    async def fake_report(acc,period):
        assert period=='today'
        return {'source':'google_live','currency':'VND','spend':205000}
    async def fake_deliver(org,message):
        collected.append((org,message))
        return {'sent':1}
    from ads_core import providers
    monkeypatch.setattr(providers,'fetch_report',fake_report)
    monkeypatch.setattr(budget_push,'deliver_to_org',fake_deliver)
    with connection() as db:
        a=dict(db.execute('SELECT * FROM accounts WHERE id=1').fetchone())
    now=1720000000
    assert asyncio.run(budget_push.check_budget_after_sample(a,now)) is True
    assert asyncio.run(budget_push.check_budget_after_sample(a,now)) is False
    assert len(collected)==1 and collected[0][0]=='orgA'
    with connection() as db:
        assert db.execute('SELECT COUNT(*) c FROM budget_events').fetchone()['c']==1
        assert db.execute("SELECT code FROM monitor_alerts").fetchone()['code'].startswith('budget_')
    async def fake_demo(acc,period):
        return {'source':'demo','currency':'VND','spend':100000000}
    monkeypatch.setattr(providers,'fetch_report',fake_demo)
    assert asyncio.run(budget_push.check_budget_after_sample(a,now+86400)) is False
    assert len(collected)==1

def test_webpush_subscription_denies_untrusted_host(client,monkeypatch,tmp_path):
    c,h=client
    key=tmp_path/'vapid.pem';key.write_text('test-key')
    monkeypatch.setenv('LHM_VAPID_PRIVATE_KEY_FILE',str(key))
    monkeypatch.setenv('LHM_VAPID_PUBLIC_KEY','example-key')
    monkeypatch.setenv('LHM_VAPID_SUBJECT','mailto:owner@example.com')
    bad={'endpoint':'https://127.0.0.1:4321/private/push/secret','keys':{'p256dh':'some-valid-looking-key','auth':'some-auth-key'}}
    assert c.post('/api/push/subscriptions',json=bad,headers=h).status_code==422
    assert c.get('/api/push/config').json()['available'] is True
    good={**bad,'endpoint':'https://fcm.googleapis.com/fcm/send/abcdefghijklmnopqrstuvwxyz'}
    assert c.post('/api/push/subscriptions',json=good,headers=h).status_code==200
    with connection() as db:
        raw=str(db.execute('SELECT sealed FROM push_subscriptions').fetchone()['sealed'])
        assert good['endpoint'] not in raw
    assert c.request('DELETE','/api/push/subscriptions',json=good,headers=h).status_code==200
