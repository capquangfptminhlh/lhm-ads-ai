"""Tests for the 2026-10-21 audit corrections.

1. OpenRouter sanitized rollup must carry complete conversion totals
   (conversions / CPA / ROAS) instead of always claiming there are none,
   while never treating a missing provider value as zero.
2. Monitoring and advisor alerts must reach the operator's optional
   Telegram channel for genuinely new alerts only, without leaking
   campaign IDs, account labels or credentials.
"""
import asyncio
import base64
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ads_core import advisor, monitoring
from ads_core import openrouter_ai as ai
from ads_core.db import connection
from ads_core.extended import app
from ads_core.security import hash_password


def _report(spend, conversions, value, source='google_live'):
    return {'source': source, 'currency': 'USD', 'spend': spend,
            'impressions': 1000, 'clicks': 100,
            'conversions': conversions, 'conversion_value': value}


def test_rollup_includes_complete_conversion_totals():
    data = {'period': 'last_7d', 'accounts': [
        {'platform': 'google', 'result': _report(200.0, 10.0, 500.0)},
        {'platform': 'google', 'result': _report(100.0, 5.0, 250.0)},
    ]}
    out = ai.sanitized_rollup(data)
    (g,) = out['groups']
    assert g['conversions'] == 15.0
    assert g['conversion_value'] == 750.0
    assert g['cpa'] == 20.0
    assert g['roas'] == 2.5
    assert 'Không có dữ liệu chuyển đổi' not in out['note']


def test_rollup_missing_conversions_are_unknown_not_zero():
    data = {'period': 'last_7d', 'accounts': [
        {'platform': 'google', 'result': _report(200.0, 10.0, 500.0)},
        # Second account's provider did not supply conversions at all.
        {'platform': 'google', 'result': {'source': 'google_live', 'currency': 'USD',
                                          'spend': 50.0, 'impressions': 100, 'clicks': 5,
                                          'conversions': None, 'conversion_value': None}},
    ]}
    out = ai.sanitized_rollup(data)
    (g,) = out['groups']
    assert g['conversions'] is None
    assert g['conversion_value'] is None
    assert g['cpa'] is None
    assert g['roas'] is None


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


def _account(c):
    assert c.post('/api/login', json={'email': 'admin@a.test',
                                       'password': 'secure_pass_1234'}).status_code == 200
    h = {'X-CSRF-Token': c.get('/api/me').json()['csrf']}
    tok = json.dumps({'client_id': 'desktop-app', 'client_secret': 'mock-secret',
                      'refresh_token': 'fake-refresh'})
    r = c.post('/api/accounts', headers=h, json={
        'platform': 'google', 'label': 'Private Customer', 'external_id': '9876543210',
        'currency': 'USD', 'token': tok})
    assert r.status_code == 200, r.text
    with connection() as db:
        return dict(db.execute('SELECT * FROM accounts WHERE id=?', (r.json()['id'],)).fetchone())


def test_advisor_telegram_only_for_new_findings(client, monkeypatch):
    acc = _account(client)
    sent = []

    async def record(message):
        sent.append(message)

    monkeypatch.setattr(advisor, 'notify_telegram', record)

    async def fetch(a):
        return [dict(id='123456789', name='Secret Campaign', status='ENABLED',
                     spend=200.0, clicks=130, impressions=10000, ctr_percent=0.3,
                     conversions=0, conversion_value=0)]

    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)
    first = asyncio.run(advisor.scan_account(acc, now=2000000000))
    assert first['scanned'] and len(sent) == 1
    assert 'low_ctr' in sent[0]
    assert '123456789' not in sent[0] and 'Secret Campaign' not in sent[0]
    assert 'Private Customer' not in sent[0] and 'fake-refresh' not in sent[0]
    # Same still-open findings on the next daily scan: no repeat message.
    second = asyncio.run(advisor.scan_account(acc, now=2000000000 + 86401))
    assert second['scanned'] and len(sent) == 1


def test_monitoring_telegram_throttled_with_alert(client, monkeypatch):
    acc = _account(client)
    monitoring.init_monitor_db()
    sent = []

    async def record(message):
        sent.append(message)

    monkeypatch.setattr(monitoring, 'notify_telegram', record)

    async def broken(a, period):
        raise HTTPException(502, 'provider down')

    monkeypatch.setattr(monitoring, 'fetch_report', broken)
    asyncio.run(monitoring.collect_account(acc, 2000000000))
    asyncio.run(monitoring.collect_account(acc, 2000000000 + 3600))
    assert len(sent) == 1
    assert 'account #' in sent[0]
    assert '9876543210' not in sent[0] and 'fake-refresh' not in sent[0]
    with connection() as db:
        rows = db.execute('SELECT * FROM monitor_alerts WHERE account_id=?', (acc['id'],)).fetchall()
        assert len(rows) == 1
