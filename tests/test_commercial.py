"""Offline license + monitor tests; never call provider APIs or real OpenRouter."""
import base64
import json
import time
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import licensing,monitoring

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'data'/'db.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'k'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','a'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as c:
        with connection() as db:
            db.execute("INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)",
                       ('billing@example.test',hash_password('long_password_123'),'org-main','admin'))
        yield c


def login(client):
    r=client.post('/api/login',json={'email':'billing@example.test','password':'long_password_123'})
    assert r.status_code==200
    return {'X-CSRF-Token':client.get('/api/me').json()['csrf']}


def signed_license(monkeypatch,device,days=30):
    key=Ed25519PrivateKey.generate()
    pub=key.public_key().public_bytes(encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
    monkeypatch.setattr(licensing,'PUBLIC_KEY_B64',base64.b64encode(pub).decode())
    ts=int(time.time())
    payload={'product':licensing.PRODUCT,'device':device,'plan':'monthly','license_id':'test-license-123',
             'issued_at':ts-10,'expires_at':ts+days*86400}
    return json.dumps({'payload':payload,'signature':base64.b64encode(key.sign(licensing.canonical(payload))).decode()})


def test_requires_auth_and_cannot_enable_without_license(client):
    assert client.get('/api/license').status_code==401
    assert client.get('/api/monitor').status_code==401
    h=login(client)
    assert client.get('/api/license').json()['active'] is False
    assert client.put('/api/monitor/settings',headers=h,json={'enabled':True,'poll_minutes':15}).status_code==402
    assert client.put('/api/monitor/settings',headers=h,json={'enabled':False,'poll_minutes':14}).status_code==422


def test_signature_device_and_renewal(client,monkeypatch):
    h=login(client)
    machine=client.get('/api/license').json()['device']
    license_text=signed_license(monkeypatch,machine)
    assert client.post('/api/license/activate',json={'license_text':license_text}).status_code==403
    result=client.post('/api/license/activate',headers=h,json={'license_text':license_text})
    assert result.status_code==200,result.text
    assert result.json()['active'] is True
    assert result.json()['expires_at']>time.time()
    assert client.put('/api/monitor/settings',headers=h,json={'enabled':True,'poll_minutes':30}).status_code==200
    other=signed_license(monkeypatch,'0'*32)
    assert client.post('/api/license/activate',headers=h,json={'license_text':other}).status_code==400 or client.post('/api/license/activate',headers=h,json={'license_text':other}).status_code==422


def test_tampering_and_expiration(client,monkeypatch):
    h=login(client)
    raw=signed_license(monkeypatch,licensing.device_id())
    data=json.loads(raw)
    data['payload']['expires_at']+=60
    with pytest.raises(ValueError):licensing.verify_signed_license(json.dumps(data))
    assert client.post('/api/license/activate',headers=h,json={'license_text':json.dumps(data)}).status_code in (400,422)
    with pytest.raises(ValueError):licensing.verify_signed_license(raw,now=int(time.time())+31*86400)


def test_read_only_background_collector(client,monkeypatch):
    h=login(client)
    raw=signed_license(monkeypatch,licensing.device_id())
    assert client.post('/api/license/activate',headers=h,json={'license_text':raw}).status_code==200
    assert client.put('/api/monitor/settings',headers=h,json={'enabled':True,'poll_minutes':15}).status_code==200
    with connection() as db:
        db.execute("INSERT INTO accounts(org_id,platform,label,external_id,currency,token_ciphertext) VALUES(?,?,?,?,?,?)",
                   ('org-main','meta','Client Private','act_1234567890','VND','cipher_mock'))
    called=[]
    async def fake_report(acc,period):
        called.append((acc['id'],period))
        return {'source':'meta_live','currency':'VND','spend':350000,'clicks':25,'impressions':1000}
    monkeypatch.setattr(monitoring,'fetch_report',fake_report)
    result=asyncio.run(monitoring.collect_once())
    assert result['checked']==1 and called[0][1]=='last_7d'
    report=client.get('/api/monitor').json()
    assert report['samples'][0]['source']=='meta_live'
    assert report['samples'][0]['period']=='last_7d'
    assert 'cipher_mock' not in json.dumps(report)


def test_no_remote_change_without_active_license(client):
    h=login(client)
    r=client.post('/api/accounts',headers=h,json={'platform':'meta','label':'Safe Meta','external_id':'act_1234567890',
            'currency':'VND','token':'test_api_placeholder_456'})
    assert r.status_code==200
    action=client.post('/api/actions',headers=h,json={'account_id':r.json()['id'],'campaign_id':'1234567890'})
    assert action.status_code==200
    r=client.post(f'/api/actions/{action.json()["id"]}/approve',headers=h)
    assert r.status_code==402
    assert client.get('/api/actions').json()[0]['status']=='pending'
