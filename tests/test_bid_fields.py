"""Bid-strategy/target/budget fields from the provider adapters and the
three playbook rules that consume them (platform_target_missed,
platform_target_headroom, manual_bidding_at_scale) plus their outcome
verification branch. All provider HTTP is faked; nothing leaves the box."""
import asyncio
import json

from ads_core import goals, optimizations
from ads_core.optimization_playbook import evaluate_campaigns, verify_outcome


class FakeResponse:
    def __init__(self, payload, code=200):
        self.payload = payload
        self.status_code = code

    def json(self):
        return self.payload

    def raise_for_status(self):
        assert self.status_code < 400


GOOGLE_ACC = {'org_id': 't', 'id': 3, 'platform': 'google',
              'external_id': '9876543210', 'currency': 'VND',
              'token_ciphertext': 'X'}


class GoogleAPI:
    def __init__(self, campaign, budget):
        self.campaign = campaign
        self.budget = budget

    async def post(self, url, **kw):
        if 'oauth2.googleapis.com' in url:
            return FakeResponse({'access_token': 'tok'})
        if url.endswith('googleAds:searchStream'):
            query = kw['json']['query']
            assert 'bidding_strategy_type' in query and 'campaign_budget.amount_micros' in query
            return FakeResponse([{'results': [{
                'campaign': self.campaign,
                'campaignBudget': self.budget,
                'metrics': {'costMicros': '2500000000', 'clicks': '500',
                            'impressions': '50000', 'conversions': 10,
                            'conversionsValue': 25000},
            }]}])
        raise AssertionError(url)


def run_google(monkeypatch, campaign, budget):
    monkeypatch.setattr(optimizations, 'account_token',
                        lambda acc: json.dumps({'client_id': 'cid',
                                                'client_secret': 'sec',
                                                'refresh_token': 'rt'}))
    return asyncio.run(optimizations.google_campaigns(GOOGLE_ACC, GoogleAPI(campaign, budget)))[0]


def test_google_target_cpa_and_daily_budget(monkeypatch):
    c = run_google(monkeypatch,
                   {'id': '12345678901', 'name': 'G', 'status': 'ENABLED',
                    'biddingStrategyType': 'TARGET_CPA',
                    'targetCpa': {'targetCpaMicros': '150000000'}},
                   {'amountMicros': '500000000', 'period': 'DAILY'})
    assert c['bidding_strategy'] == 'TARGET_CPA'
    assert c['bid_target_cpa'] == 150.0
    assert c['bid_target_roas'] is None
    assert c['daily_budget'] == 500.0
    assert c['cpa'] == 250.0 and c['roas'] == 10.0


def test_google_maximize_fallback_and_non_daily_budget(monkeypatch):
    c = run_google(monkeypatch,
                   {'id': '12345678901', 'name': 'G', 'status': 'ENABLED',
                    'biddingStrategyType': 'MAXIMIZE_CONVERSIONS',
                    'maximizeConversions': {'targetCpaMicros': '200000000'}},
                   {'amountMicros': '900000000', 'period': 'CUSTOM_PERIOD'})
    assert c['bid_target_cpa'] == 200.0
    assert c['daily_budget'] is None  # not a daily budget -> never presented as one


META_ACC = {'org_id': 't', 'id': 8, 'platform': 'meta',
            'external_id': 'act_1234567890', 'currency': 'VND',
            'token_ciphertext': 'X'}


class MetaAPI:
    async def get(self, url, **kw):
        if url.endswith('/campaigns'):
            assert 'bid_strategy' in kw['params']['fields']
            return FakeResponse({'data': [{
                'id': '12345678901', 'name': 'M', 'status': 'ACTIVE',
                'effective_status': 'ACTIVE',
                'bid_strategy': 'LOWEST_COST_WITH_BID_CAP',
                'daily_budget': '150000', 'lifetime_budget': '900000'}]})
        if url.endswith('/adsets'):
            return FakeResponse({'data': []})
        if url.endswith('/insights'):
            return FakeResponse({'data': []})
        raise AssertionError(url)

    async def post(self, *a, **kw):
        raise AssertionError('read-only')


def test_meta_bid_fields_minor_units(monkeypatch):
    monkeypatch.setattr(optimizations, 'account_token', lambda acc: 'TOK')
    monkeypatch.setattr(goals, 'goal_for', lambda org, aid: None)
    c = asyncio.run(optimizations.meta_campaigns(META_ACC, MetaAPI()))[0]
    assert c['bidding_strategy'] == 'LOWEST_COST_WITH_BID_CAP'
    assert c['daily_budget'] == 1500.0       # 150000 minor units (cents)
    assert c['lifetime_budget'] == 9000.0
    assert c['bid_target_cpa'] is None       # ad-set level on Meta: not claimed


def camp(**kw):
    base = dict(id='1', name='C', status='ENABLED', spend=1_000_000.0, clicks=300,
                impressions=30000, ctr_percent=1.0, conversions=20,
                conversion_value=20_000_000.0, cpa=50_000.0, roas=20.0,
                bidding_strategy=None, bid_target_cpa=None, bid_target_roas=None,
                daily_budget=None)
    base.update(kw)
    return base


def codes(findings):
    return {f['code'] for f in findings}


def test_platform_target_missed_cpa_and_roas():
    f = evaluate_campaigns([camp(bid_target_cpa=30_000.0)], 'google', 'VND')
    hit = next(x for x in f if x['code'] == 'platform_target_missed')
    assert hit['level'] == 'critical'  # 50k vs 30k = 1.67x
    f = evaluate_campaigns([camp(bid_target_roas=30.0)], 'google', 'VND')
    assert 'platform_target_missed' in codes(f)  # roas 20 < 30/1.3
    # Within tolerance -> silent; too few conversions -> silent.
    assert 'platform_target_missed' not in codes(
        evaluate_campaigns([camp(bid_target_cpa=45_000.0)], 'google', 'VND'))
    assert 'platform_target_missed' not in codes(
        evaluate_campaigns([camp(bid_target_cpa=30_000.0, conversions=3)], 'google', 'VND'))


def test_platform_target_headroom_and_conflict():
    f = evaluate_campaigns([camp(bid_target_cpa=70_000.0)], 'google', 'VND')
    assert 'platform_target_headroom' in codes(f)  # 50k < 0.8*70k
    f = evaluate_campaigns([camp(bid_target_roas=10.0)], 'google', 'VND')
    assert 'platform_target_headroom' in codes(f)  # roas 20 > 1.25*10


def test_manual_bidding_at_scale():
    f = evaluate_campaigns([camp(bidding_strategy='MANUAL_CPC', conversions=45)],
                           'google', 'VND')
    assert 'manual_bidding_at_scale' in codes(f)
    f = evaluate_campaigns([camp(bidding_strategy='MANUAL_CPC', conversions=10)],
                           'google', 'VND')
    assert 'manual_bidding_at_scale' not in codes(f)  # below volume threshold
    f = evaluate_campaigns([camp(bidding_strategy='LOWEST_COST_WITH_BID_CAP',
                                 conversions=45, status='ACTIVE')], 'meta', 'VND')
    assert 'manual_bidding_at_scale' in codes(f)
    f = evaluate_campaigns([camp(bidding_strategy='TARGET_CPA', conversions=45)],
                           'google', 'VND')
    assert 'manual_bidding_at_scale' not in codes(f)


def test_verify_outcome_platform_codes():
    base = camp(bid_target_cpa=30_000.0, cpa=50_000.0)
    now = camp(bid_target_cpa=30_000.0, cpa=32_000.0)
    assert verify_outcome(base, now, 'platform_target_missed') == 'improved'
    worse = camp(bid_target_cpa=30_000.0, cpa=60_000.0)
    assert verify_outcome(base, worse, 'platform_target_missed') == 'worsened'
    thin = camp(bid_target_cpa=30_000.0, cpa=32_000.0, conversions=2)
    assert verify_outcome(base, thin, 'platform_target_missed') == 'insufficient_data'
