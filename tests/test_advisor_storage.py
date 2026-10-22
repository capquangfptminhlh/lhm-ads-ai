"""Advisor storage efficiency + integrity (sprint a18).

Covers, through the real scan code path (provider fetch stubbed exactly
like tests/test_advisor.py):
  1. The (org_id, account_id, resolved_at) findings index exists after
     init_advisor_db() and is the index SQLite picks for the per-scan
     open-findings lookup.
  2. Snapshot pruning actually bounds growth: >12 scans leave exactly
     the newest 12 snapshots for that account, and pruning one account
     never touches another account's snapshots.
  3. advisor_outcomes never accumulates a second verdict row for the
     same finding across repeated scans (finding_id is the PRIMARY KEY,
     inserts are INSERT OR IGNORE, and verdicted findings drop out of
     the pending query — this test pins all three layers end to end).
"""
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


def account(c, h, external_id):
    tok = json.dumps({'client_id': 'desktop-app', 'client_secret': 'mock-secret',
                      'refresh_token': 'fake-refresh'})
    r = c.post('/api/accounts', headers=h, json={
        'platform': 'google', 'label': 'Storage', 'external_id': external_id,
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


T0 = 2_000_000_000
DAY_S = 86401  # > advisor.DAY and > advisor.RETRY, so every call really scans


def test_findings_account_index_exists_and_is_used(client):
    advisor.init_advisor_db()
    with connection() as db:
        cols = [r['name'] for r in db.execute(
            "PRAGMA index_info('idx_advisor_findings_account')")]
        assert cols == ['org_id', 'account_id', 'resolved_at']
        plan = [r['detail'] for r in db.execute(
            '''EXPLAIN QUERY PLAN SELECT campaign_id,rule_code FROM advisor_findings
               WHERE org_id=? AND account_id=? AND resolved_at IS NULL''', ('A', 1))]
    assert any('idx_advisor_findings_account' in step for step in plan), plan


def test_snapshot_pruning_keeps_newest_12_per_account(client, monkeypatch):
    h = login(client)
    aid = account(client, h, '9876543210')
    other = account(client, h, '9876543211')

    async def fetch(acc):
        return [campaign()]
    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)

    scans = 15
    for i in range(scans):
        result = asyncio.run(advisor.scan_account(acc_row(aid), now=T0 + i * DAY_S))
        assert result['scanned'], result
    for i in range(3):
        result = asyncio.run(advisor.scan_account(acc_row(other), now=T0 + i * DAY_S))
        assert result['scanned'], result

    with connection() as db:
        kept = [r['taken_at'] for r in db.execute(
            'SELECT taken_at FROM advisor_snapshots WHERE account_id=? ORDER BY taken_at',
            (aid,)).fetchall()]
        other_kept = db.execute(
            'SELECT COUNT(*) c FROM advisor_snapshots WHERE account_id=?',
            (other,)).fetchone()['c']
    assert len(kept) == 12
    # Exactly the newest 12 scan times survive; the oldest 3 were pruned.
    assert kept == [T0 + i * DAY_S for i in range(scans - 12, scans)]
    # Pruning is scoped per (org_id, account_id): the other account is intact.
    assert other_kept == 3


def test_outcome_verdict_written_once_across_repeated_scans(client, monkeypatch):
    from ads_core.goals import init_goals_db
    h = login(client)
    aid = account(client, h, '9876543210')
    init_goals_db()
    with connection() as db:
        db.execute('''INSERT INTO ads_goals(org_id,account_id,enabled,objective,target,
                      min_conversions,min_clicks,currency)
                      VALUES('A',?,1,'cpa',200000,5,100,'VND')''', (aid,))

    state = {'rows': [campaign()]}  # CPA 250k vs 200k target -> cpa_above_target
    async def fetch(acc):
        return state['rows']
    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)
    acc = acc_row(aid)

    asyncio.run(advisor.scan_account(acc, now=T0))
    with connection() as db:
        fid = db.execute(
            "SELECT id FROM advisor_findings WHERE account_id=? AND rule_code='cpa_above_target'",
            (aid,)).fetchone()['id']

    state['rows'] = [campaign(cpa=180_000.0)]  # improved below target
    for days in (8, 9, 10):  # verdict lands on day 8; days 9-10 must not duplicate it
        result = asyncio.run(advisor.scan_account(acc, now=T0 + days * 86400))
        assert result['scanned'], result

    with connection() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT finding_id,verdict,checked_at FROM advisor_outcomes WHERE finding_id=?',
            (fid,)).fetchall()]
        total = db.execute('SELECT COUNT(*) c FROM advisor_outcomes').fetchone()['c']
    assert len(rows) == 1
    assert rows[0]['verdict'] == 'improved'
    assert rows[0]['checked_at'] == T0 + 8 * 86400  # first verdict stands, never rewritten
    assert total == 1
