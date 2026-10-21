"""Dashboard source isolation and unbounded account summaries (offline)."""
import base64
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core.providers import demo_report


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'dashboard.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'd'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','s'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as client:
        with connection() as db:
            db.execute("INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)",
                       ('dashboard@example.test',hash_password('test-password-987654'),'dash','admin'))
        assert client.post('/api/login',json={
            'email':'dashboard@example.test','password':'test-password-987654'}).status_code==200
        yield client


def add(platform, label, currency='VND', org='dash'):
    with connection() as db:
        return db.execute("INSERT INTO accounts(org_id,platform,label,external_id,currency) VALUES(?,?,?,?,?)",
                          (org,platform,label,label.replace(' ','_'),currency)).lastrowid


def report(acc, spend=100):
    return {'source': 'google_live' if acc['platform']=='google' else 'meta_live',
            'currency':acc['currency'],'spend':spend,'impressions':100,
            'clicks':10,'ctr':10,'daily':[{'date':'2026-10-20','spend':spend}],
            'conversions':None,'conversion_value':None,'conversion_action_type':None,
            'cpa':None,'roas':None}


def test_more_than_twenty_accounts_and_demo_excluded(api, monkeypatch):
    import ads_core.app as appmod
    for i in range(27):add('meta',f'Real {i}')
    add('demo','Preview')
    add('meta','Other Tenant',org='someone-else')
    async def fake(acc,period):
        return demo_report(acc['id'],period) if acc['platform']=='demo' else report(acc)
    monkeypatch.setattr(appmod,'fetch_report',fake)
    payload=api.get('/api/summary').json()
    assert len(payload['accounts'])==28
    assert payload['totals']['total_accounts']==28
    assert payload['totals']['included_accounts']==27
    assert payload['totals']['spend']==2700
    assert payload['totals']['clicks']==270
    assert payload['totals']['contains_demo'] is False
    assert payload['totals']['has_demo_accounts'] is True
    assert payload['totals']['data_mode']=='live'
    assert 'Other Tenant' not in str(payload)


def test_only_demo_explicit_preview(api):
    add('demo','Preview')
    payload=api.get('/api/summary').json()
    assert payload['totals']['data_mode']=='demo'
    assert payload['totals']['contains_demo'] is True
    assert payload['totals']['included_accounts']==1
    assert payload['totals']['spend']>0


def test_failed_live_does_not_fall_back_to_demo(api,monkeypatch):
    import ads_core.app as appmod
    add('demo','Preview')
    add('meta','Broken Live')
    async def fake(acc,period):
        if acc['platform']=='demo':return demo_report(acc['id'],period)
        raise HTTPException(502,'Ads credentials unavailable')
    monkeypatch.setattr(appmod,'fetch_report',fake)
    data=api.get('/api/summary').json()
    t=data['totals']
    assert t['data_mode']=='live' and t['contains_demo'] is False
    assert t['included_accounts']==0 and t['failed_accounts']==1
    assert t['spend'] is None and t['by_currency']=={}
    assert data['accounts'][1]['error']=='Ads credentials unavailable'


def test_multi_currency_and_grounded_conversion_metrics(api,monkeypatch):
    import ads_core.app as appmod
    add('google','A','USD')
    add('google','B','USD')
    add('meta','C','VND')
    async def fake(acc,period):
        r=report(acc,120 if acc['currency']=='USD' else 500)
        if acc['platform']=='google':
            r.update(conversions=3,conversion_value=360,
                     conversion_action_type='google_all_conversions',cpa=40,roas=3)
        return r
    monkeypatch.setattr(appmod,'fetch_report',fake)
    t=api.get('/api/summary').json()['totals']
    assert t['spend'] is None and t['currency'] is None
    assert t['by_currency']['USD']['spend']==240
    assert t['by_currency']['VND']['spend']==500
    assert t['ctr']==10
    assert t['conversions'] is None and t['roas'] is None
