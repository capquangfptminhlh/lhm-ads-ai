"""Meta frequency/reach adapter parsing + audience_fatigue_risk playbook rule.

Offline only: Meta HTTP is faked with the same patterns as
tests/test_meta_conversion.py; the playbook is exercised as a pure function.
Contract under test: frequency/reach are None when absent — never faked as 0 —
and the fatigue rule fires on (frequency >= 4.0 with known CTR < 1.0%) or
(frequency >= 6.0 regardless of CTR), always with >= 1000 impressions.
"""
import asyncio

from ads_core import goals, optimizations
from ads_core import optimization_playbook as pb


# ---------------------------------------------------------------------------
# Adapter: frequency/reach parsing (Meta insights)
# ---------------------------------------------------------------------------
ACCOUNT = {'org_id': 'tenant-a', 'id': 8, 'platform': 'meta',
           'external_id': 'act_1234567890', 'currency': 'USD',
           'token_ciphertext': 'ENCRYPTED'}
CAMPAIGN = {'id': '12345678901', 'name': 'Campaign', 'status': 'ACTIVE',
            'effective_status': 'ACTIVE'}


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


class MetaAPI:
    def __init__(self, rows):
        self.rows = rows
        self.requests = []

    async def get(self, url, **kw):
        self.requests.append((url, kw))
        if url.endswith('/campaigns'):
            return FakeResponse({'data': [CAMPAIGN]})
        if url.endswith('/insights'):
            return FakeResponse({'data': self.rows})
        if url.endswith('/adsets'):
            return FakeResponse({'data': []})
        raise AssertionError('No other HTTP allowed')

    async def post(self, *args, **kwargs):
        raise AssertionError('Read-only campaign insights must never modify Ads')


def insight_row(**kw):
    row = {'campaign_id': CAMPAIGN['id'], 'spend': '120', 'clicks': '40',
           'impressions': '5000'}
    row.update(kw)
    return row


def run_meta(monkeypatch, rows):
    monkeypatch.setattr(optimizations, 'account_token', lambda acc: 'MOCK_TOKEN')
    monkeypatch.setattr(goals, 'goal_for', lambda org, aid: None)
    client = MetaAPI(rows)
    campaigns = asyncio.run(optimizations.meta_campaigns(ACCOUNT, client))
    assert len(campaigns) == 1
    return campaigns[0], client


def test_adapter_frequency_reach_parsed(monkeypatch):
    c, client = run_meta(monkeypatch, [insight_row(frequency='4.25', reach='18234')])
    assert c['frequency'] == 4.25 and isinstance(c['frequency'], float)
    assert c['reach'] == 18234 and isinstance(c['reach'], int)
    fields = client.requests[1][1]['params']['fields']
    assert 'frequency' in fields and 'reach' in fields


def test_adapter_frequency_reach_absent_is_none_never_zero(monkeypatch):
    c, _ = run_meta(monkeypatch, [insight_row()])
    assert 'frequency' in c and 'reach' in c
    assert c['frequency'] is None and c['reach'] is None


def test_adapter_frequency_reach_zero_and_garbage_is_none(monkeypatch):
    c, _ = run_meta(monkeypatch, [insight_row(frequency='0', reach='0')])
    assert c['frequency'] is None and c['reach'] is None
    c, _ = run_meta(monkeypatch, [insight_row(frequency='abc', reach='x1')])
    assert c['frequency'] is None and c['reach'] is None


def test_adapter_no_insight_row_keeps_none_keys(monkeypatch):
    c, _ = run_meta(monkeypatch, [])
    assert c['frequency'] is None and c['reach'] is None


# ---------------------------------------------------------------------------
# Playbook: audience_fatigue_risk thresholds
# ---------------------------------------------------------------------------
def campaign(**kw):
    base = {'id': '111', 'name': 'C', 'status': 'ACTIVE', 'spend': 100.0,
            'clicks': 20, 'impressions': 5000, 'ctr_percent': 0.4,
            'conversions': None, 'conversion_value': None, 'cpa': None,
            'roas': None, 'frequency': None, 'reach': None}
    base.update(kw)
    return base


def fatigue(findings):
    return [f for f in findings if f['code'] == 'audience_fatigue_risk']


def evaluate(c, platform='meta'):
    return pb.evaluate_campaigns([c], platform, 'USD', None)


def test_fatigue_fires_freq4_with_weak_ctr():
    hits = fatigue(evaluate(campaign(frequency=4.5, ctr_percent=0.4)))
    assert len(hits) == 1
    hit = hits[0]
    assert hit['level'] == 'review' and hit['category'] == 'structure'
    assert '4.50' in hit['message']  # message carries the frequency number
    text = hit['playbook']['why'] + ' ' + ' '.join(hit['playbook']['actions'])
    assert 'checklist' in text.lower() and 'KHÔNG nhìn thấy' in text


def test_fatigue_boundary_freq_exactly_4():
    assert len(fatigue(evaluate(campaign(frequency=4.0, ctr_percent=0.99)))) == 1
    assert fatigue(evaluate(campaign(frequency=3.99, ctr_percent=0.4))) == []


def test_fatigue_freq4_needs_known_weak_ctr():
    # CTR healthy -> no fire below the high-frequency branch.
    assert fatigue(evaluate(campaign(frequency=4.5, ctr_percent=1.5))) == []
    # CTR exactly 1.0 is not "< 1.0" -> no fire.
    assert fatigue(evaluate(campaign(frequency=4.5, ctr_percent=1.0))) == []
    # CTR unknown -> branch (a) cannot conclude.
    assert fatigue(evaluate(campaign(frequency=4.5, ctr_percent=None))) == []


def test_fatigue_fires_freq6_regardless_of_ctr():
    assert len(fatigue(evaluate(campaign(frequency=6.0, ctr_percent=2.5)))) == 1
    assert len(fatigue(evaluate(campaign(frequency=7.2, ctr_percent=None)))) == 1
    assert fatigue(evaluate(campaign(frequency=5.99, ctr_percent=2.5))) == []


def test_fatigue_requires_min_impressions_and_frequency():
    assert fatigue(evaluate(campaign(frequency=7.0, impressions=999))) == []
    assert fatigue(evaluate(campaign(frequency=None, ctr_percent=0.4))) == []
    assert fatigue(evaluate(campaign(frequency=7.0, impressions=None))) == []


def test_fatigue_is_meta_only():
    assert fatigue(evaluate(campaign(frequency=7.0), platform='google')) == []


def test_fatigue_registered_in_playbook():
    entry = pb._BY_CODE['audience_fatigue_risk']
    assert entry['platform'] == 'meta'
    assert entry['category'] == 'structure'
    assert entry['severity'] == 'review'
    assert pb.CONDITIONS['audience_fatigue_risk'] is pb._cond_audience_fatigue_risk


# ---------------------------------------------------------------------------
# verify_outcome: judged by CTR movement, like low_ctr
# ---------------------------------------------------------------------------
def test_verify_outcome_fatigue_uses_ctr():
    base = campaign(ctr_percent=0.5, frequency=5.0)
    assert pb.verify_outcome(base, campaign(ctr_percent=0.8), 'audience_fatigue_risk') == 'improved'
    assert pb.verify_outcome(base, campaign(ctr_percent=0.4), 'audience_fatigue_risk') == 'worsened'
    assert pb.verify_outcome(base, campaign(ctr_percent=0.51), 'audience_fatigue_risk') == 'unchanged'
    assert pb.verify_outcome(base, campaign(ctr_percent=None), 'audience_fatigue_risk') == 'insufficient_data'
    assert pb.verify_outcome(campaign(ctr_percent=0), campaign(ctr_percent=0.8),
                             'audience_fatigue_risk') == 'insufficient_data'
