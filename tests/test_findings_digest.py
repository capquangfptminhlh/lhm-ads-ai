"""Offline tests for advisor.findings_digest and its scan-completion wiring.

The digest is a read-only summary over the existing advisor_findings table:
counts of ACTIVE findings by level plus the newest codes with their
playbook catalog titles. Privacy contract under test: nothing in the
digest or in the enriched Telegram alert carries campaign names, account
labels or credentials — codes, counts and the internal account number only.
"""
import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import advisor


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'ads.sqlite3'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'x' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'a' * 48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setattr(advisor, 'license_required', lambda: {'active': True})
    advisor.init_advisor_db()
    return tmp_path


def add_finding(org, account_id, code, severity, *, first_seen=1000,
                resolved=None, acknowledged=None, campaign='camp1'):
    with connection() as db:
        db.execute('''INSERT INTO advisor_findings(org_id,account_id,campaign_id,
            rule_code,severity,message,first_seen_at,last_seen_at,
            acknowledged_at,resolved_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                   (org, account_id, campaign, code, severity, 'msg',
                    first_seen, first_seen, acknowledged, resolved))


def test_digest_counts_active_by_level(env):
    add_finding('A', 7, 'cpa_above_target', 'high', campaign='c1')
    add_finding('A', 7, 'platform_target_missed', 'high', campaign='c2')
    add_finding('A', 7, 'low_ctr', 'review', campaign='c3')
    # Acknowledged but unresolved still counts as active.
    add_finding('A', 7, 'dead_campaign', 'review', campaign='c4', acknowledged=900)
    # Resolved findings never count.
    add_finding('A', 7, 'spend_no_conversions', 'review', campaign='c5', resolved=950)
    add_finding('A', 7, 'roas_above_target_scale', 'opportunity', campaign='c6')
    d = advisor.findings_digest('A', 7)
    assert d['account_id'] == 7
    assert d['active_counts'] == {'critical': 2, 'review': 2, 'opportunity': 1}
    assert d['active_total'] == 5


def test_digest_tenant_and_account_isolation(env):
    add_finding('A', 7, 'low_ctr', 'review')
    add_finding('B', 7, 'low_ctr', 'high')
    add_finding('A', 8, 'low_ctr', 'high')
    d = advisor.findings_digest('A', 7)
    assert d['active_total'] == 1
    assert d['active_counts'] == {'critical': 0, 'review': 1, 'opportunity': 0}


def test_digest_empty_account(env):
    d = advisor.findings_digest('A', 404)
    assert d['active_counts'] == {'critical': 0, 'review': 0, 'opportunity': 0}
    assert d['active_total'] == 0
    assert d['new'] == []


def test_digest_new_titles_from_playbook_catalog(env):
    d = advisor.findings_digest(
        'A', 7, max_new_titles=10,
        new_codes=['cpa_above_target', 'roas_above_target_scale',
                   'cpa_above_goal', 'totally_unknown_code'])
    by_code = {item['code']: item['title'] for item in d['new']}
    # Playbook codes resolve to their shipped catalog titles.
    assert by_code['cpa_above_target'] == 'CPA vượt mục tiêu — giảm tốc theo bước nhỏ'
    assert by_code['roas_above_target_scale'] == 'ROAS vượt mục tiêu — cơ hội tăng ngân sách theo bước'
    # Legacy/unknown codes are listed with no invented title.
    assert by_code['cpa_above_goal'] is None
    assert by_code['totally_unknown_code'] is None


def test_digest_new_limit_and_dedup(env):
    codes = ['low_ctr', 'low_ctr', 'dead_campaign', 'cpa_above_target',
             'roas_below_target']
    d = advisor.findings_digest('A', 7, new_codes=codes)
    assert [item['code'] for item in d['new']] == [
        'low_ctr', 'dead_campaign', 'cpa_above_target']
    d = advisor.findings_digest('A', 7, new_codes=codes, max_new_titles=2)
    assert [item['code'] for item in d['new']] == ['low_ctr', 'dead_campaign']


def test_digest_new_defaults_to_latest_active_findings(env):
    add_finding('A', 7, 'low_ctr', 'review', first_seen=100, campaign='c1')
    add_finding('A', 7, 'cpa_above_target', 'high', first_seen=300, campaign='c2')
    # Same code on another campaign: listed once, latest position wins.
    add_finding('A', 7, 'low_ctr', 'review', first_seen=200, campaign='c3')
    # A resolved newer finding must not appear.
    add_finding('A', 7, 'dead_campaign', 'review', first_seen=400,
                campaign='c4', resolved=500)
    d = advisor.findings_digest('A', 7)
    assert [item['code'] for item in d['new']] == ['cpa_above_target', 'low_ctr']
    assert d['new'][0]['title'] is not None


# ---------------------------------------------------------------------------
# Scan-completion wiring: digest in the result + enriched Telegram alert.
# ---------------------------------------------------------------------------

@pytest.fixture
def client(env):
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       ('admin@a.test', hash_password('secure_pass_1234'), 'A', 'admin'))
        yield c


def login(c):
    assert c.post('/api/login', json={'email': 'admin@a.test',
                                      'password': 'secure_pass_1234'}).status_code == 200
    return {'X-CSRF-Token': c.get('/api/me').json()['csrf']}


def test_scan_returns_digest_and_enriches_telegram(client, monkeypatch):
    import json
    h = login(client)
    tok = json.dumps({'client_id': 'desktop-app', 'client_secret': 'mock-secret',
                      'refresh_token': 'fake-refresh'})
    r = client.post('/api/accounts', headers=h, json={
        'platform': 'google', 'label': 'Private Customer',
        'external_id': '9876543210', 'currency': 'USD', 'token': tok})
    assert r.status_code == 200, r.text
    aid = r.json()['id']

    async def fetch(acc):
        return [dict(id='123456789', name='Secret Account Campaign',
                     status='ENABLED', spend=200.0, clicks=130,
                     impressions=10000, ctr_percent=0.3, conversions=0,
                     conversion_value=0)]
    monkeypatch.setattr(advisor, 'list_live_campaigns', fetch)

    sent = []

    async def fake_notify(message):
        sent.append(message)
    monkeypatch.setattr(advisor, 'notify_telegram', fake_notify)

    with connection() as db:
        acc = dict(db.execute('SELECT * FROM accounts WHERE id=?', (aid,)).fetchone())
    result = asyncio.run(advisor.scan_account(acc, now=2000000000))
    assert result['scanned']
    digest = result['digest']
    # The seeded campaign yields two review-level findings (legacy + playbook
    # dedup keeps exactly two, as in tests/test_advisor.py).
    assert digest['active_total'] == result['recommendations'] == 2
    assert digest['active_counts'] == {'critical': 0, 'review': 2, 'opportunity': 0}
    # Legacy duplicates are dropped in favour of the playbook versions.
    assert {item['code'] for item in digest['new']} == {
        'spend_no_conversions', 'low_ctr'}

    # Exactly one Telegram message, enriched with level counts, still free
    # of campaign names / account labels / credentials.
    assert len(sent) == 1
    message = sent[0]
    assert '0 critical, 2 review, 0 opportunity' in message
    assert 'tổng 2' in message
    assert f'account #{aid}' in message
    assert 'Secret Account Campaign' not in message
    assert 'Private Customer' not in message
    assert 'fake-refresh' not in message and 'mock-secret' not in message
