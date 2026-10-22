"""Integration wiring for the LHM Optimization Loop (coordinator):
playbook findings stored by the advisor with playbook detail, the older
goal codes deduplicated against the richer playbook rules, per-account
snapshots feeding baselines on later scans, account-level findings that
resolve, and outcome verdicts after 7+ days. Offline; provider fetch is
stubbed exactly like tests/test_advisor.py does."""
import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import advisor


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'ads.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'x' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'a' * 48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setattr(advisor, 'license_required', lambda: {'active': True})
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       ('admin@a.test', hash_password('secure_pass_1234'), 'A', 'admin'))
        yield c


def login(c):
    assert c.post('/api/login', json={'email': 'admin@a.test',
                                      'password': 'secure_pass_1234'}).status_code == 200
    return {'X-CSRF-Token': c.get('/api/me').json()['csrf']}


def account(c, h):
    tok = json.dumps({'client_id': 'desktop-app', 'client_secret': 'mock-secret',
                      'refresh_token': 'fake-refresh'})
    r = c.post('/api/accounts', headers=h, json={
        'platform': 'google', 'label': 'Wiring', 'external_id': '9876543210',
        'currency': 'VND', 'token': tok})
    assert r.status_code == 200, r.text
    return r.json()['id']


def acc_row(aid):
    with connection() as db:
        return dict(db.execute('SELECT * FROM accounts WHERE id=?', (aid,)).fetchone())


def campaign(cid='111', **kw):
    base = dict(id=cid, name='C', status='ENABLED', spend=5_000_000.0, clicks=200,
                impressions=20000, ctr_percent=1.0, conversions=20,
                conversion_value=200_000_000.0, cpa=250_000.0, roas=40.0)
    base.update(kw)
    return base


def set_goal(aid, objective='cpa', target=200_000.0):
    from ads_core.goals import init_goals_db
    init_goals_db()
    with connection() as db:
        db.execute('''INSERT INTO ads_goals(org_id,account_id,enabled,objective,target,
                      min_conversions,min_clicks,currency)
                      VALUES('A',?,1,?,?,5,100,'VND')''',
                   (aid, objective, target))


def findings_of(aid):
    with connection() as db:
        return [dict(r) for r in db.execute(
            'SELECT * FROM advisor_findings WHERE account_id=?', (aid,)).fetchall()]


def test_playbook_findings_stored_with_detail_and_dedup(client, monkeypatch):
    h = login(client)
    aid = account(client, h)
    set_goal(aid, 'cpa', 200_000.0)  # campaign CPA 250k = 1.25x target
    async def fetch(acc):
        return [campaign()]
    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)
    result = asyncio.run(advisor.scan_account(acc_row(aid), now=2_000_000_000))
    assert result['scanned']
    rows = findings_of(aid)
    codes = {r['rule_code'] for r in rows}
    assert 'cpa_above_target' in codes
    assert 'cpa_above_goal' not in codes  # richer playbook rule wins, no duplicate
    row = next(r for r in rows if r['rule_code'] == 'cpa_above_target')
    detail = json.loads(row['detail'])
    assert detail['playbook']['actions'] and detail['playbook']['guardrails']
    # A snapshot was stored for future baselines.
    with connection() as db:
        assert db.execute('SELECT COUNT(*) c FROM advisor_snapshots WHERE account_id=?',
                          (aid,)).fetchone()['c'] == 1


def test_baseline_drift_fires_on_later_scan(client, monkeypatch):
    h = login(client)
    aid = account(client, h)
    state = {'rows': [campaign(cpa=250_000.0, roas=40.0)]}
    async def fetch(acc):
        return state['rows']
    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)
    acc = acc_row(aid)
    t0 = 2_000_000_000
    for i in range(3):  # three healthy history scans build the baseline
        asyncio.run(advisor.scan_account(acc, now=t0 + i * 86401))
    state['rows'] = [campaign(cpa=400_000.0, roas=40.0)]  # CPA drifts +60%
    asyncio.run(advisor.scan_account(acc, now=t0 + 3 * 86401))
    codes = {r['rule_code'] for r in findings_of(aid) if r['resolved_at'] is None}
    assert 'cpa_drift_vs_baseline' in codes


def test_outcome_verdict_after_seven_days(client, monkeypatch):
    h = login(client)
    aid = account(client, h)
    set_goal(aid, 'cpa', 200_000.0)
    state = {'rows': [campaign()]}
    async def fetch(acc):
        return state['rows']
    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)
    acc = acc_row(aid)
    t0 = 2_000_000_000
    asyncio.run(advisor.scan_account(acc, now=t0))
    assert any(r['rule_code'] == 'cpa_above_target' for r in findings_of(aid))
    state['rows'] = [campaign(cpa=180_000.0)]  # CPA improved below target
    asyncio.run(advisor.scan_account(acc, now=t0 + 8 * 86400))
    with connection() as db:
        verdicts = [dict(r) for r in db.execute(
            '''SELECT o.verdict FROM advisor_outcomes o
               JOIN advisor_findings f ON f.id=o.finding_id
               WHERE f.account_id=? AND f.rule_code='cpa_above_target' ''', (aid,)).fetchall()]
    assert verdicts and verdicts[0]['verdict'] == 'improved'


def test_account_level_finding_resolves(client, monkeypatch):
    h = login(client)
    aid = account(client, h)
    many_small = [campaign(cid=str(100 + i), conversions=2, spend=100_000.0,
                           cpa=50_000.0, roas=None, conversion_value=None)
                  for i in range(5)]
    state = {'rows': many_small}
    async def fetch(acc):
        return state['rows']
    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)
    acc = acc_row(aid)
    t0 = 2_000_000_000
    asyncio.run(advisor.scan_account(acc, now=t0))
    frag = [r for r in findings_of(aid) if r['rule_code'] == 'account_fragmentation']
    assert frag and frag[0]['campaign_id'] == 'ACCOUNT'
    state['rows'] = [campaign()]  # consolidated: one healthy campaign
    asyncio.run(advisor.scan_account(acc, now=t0 + 86401))
    frag = [r for r in findings_of(aid) if r['rule_code'] == 'account_fragmentation']
    assert frag[0]['resolved_at'] is not None
