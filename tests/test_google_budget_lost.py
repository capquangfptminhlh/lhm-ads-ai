"""Budget-lost impression share parsing in the Google adapter.

metrics.search_budget_lost_impression_share must surface as campaign key
'budget_lost_is' (float 0..1). Absent or non-numeric values stay None
(unknown) — never 0, which would falsely claim "no budget loss".
All provider HTTP is faked; nothing leaves the box.
"""
import asyncio
import json

from ads_core import optimizations


class Response:
    def __init__(self, body, code=200):
        self.body = body
        self.status_code = code

    def json(self):
        return self.body

    def raise_for_status(self):
        assert self.status_code < 400


GOOGLE_ACC = {'org_id': 't', 'id': 3, 'platform': 'google',
              'external_id': '9876543210', 'currency': 'VND',
              'token_ciphertext': 'X'}


class GoogleAPI:
    """Fake httpx client: routes the OAuth token POST and searchStream."""

    def __init__(self, metrics):
        self.metrics = metrics
        self.queries = []

    async def post(self, url, **kwargs):
        if url == 'https://oauth2.googleapis.com/token':
            assert kwargs['data']['refresh_token'] == 'private-refresh'
            return Response({'access_token': 'transient'})
        if url.endswith('/googleAds:searchStream'):
            self.queries.append(kwargs['json']['query'])
            return Response([{'results': [{
                'campaign': {'id': '12345678901', 'name': 'Search Campaign',
                             'status': 'ENABLED'},
                'metrics': self.metrics,
            }]}])
        raise AssertionError('Unexpected external HTTP: ' + url)


BASE_METRICS = {'costMicros': '250000000', 'clicks': '120',
                'impressions': '60000', 'conversions': 4,
                'conversionsValue': 900000}


def run_google(monkeypatch, metrics):
    monkeypatch.setattr(optimizations, 'account_token',
                        lambda acc: json.dumps({'client_id': 'cid',
                                                'client_secret': 'sec',
                                                'refresh_token': 'private-refresh'}))
    client = GoogleAPI(metrics)
    campaigns = asyncio.run(optimizations.google_campaigns(GOOGLE_ACC, client))
    assert len(campaigns) == 1
    return campaigns[0], client


def test_budget_lost_is_parsed_as_ratio(monkeypatch):
    campaign, _ = run_google(monkeypatch, dict(
        BASE_METRICS, searchBudgetLostImpressionShare=0.35))
    assert campaign['budget_lost_is'] == 0.35


def test_budget_lost_is_zero_is_a_real_zero(monkeypatch):
    # An explicit 0 from the API is a measured value, distinct from None.
    campaign, _ = run_google(monkeypatch, dict(
        BASE_METRICS, searchBudgetLostImpressionShare=0.0))
    assert campaign['budget_lost_is'] == 0.0
    assert campaign['budget_lost_is'] is not None


def test_budget_lost_is_absent_is_none(monkeypatch):
    campaign, _ = run_google(monkeypatch, dict(BASE_METRICS))
    assert campaign['budget_lost_is'] is None


def test_budget_lost_is_non_numeric_is_none(monkeypatch):
    campaign, _ = run_google(monkeypatch, dict(
        BASE_METRICS, searchBudgetLostImpressionShare='n/a'))
    assert campaign['budget_lost_is'] is None


def test_query_requests_budget_lost_field(monkeypatch):
    _, client = run_google(monkeypatch, dict(BASE_METRICS))
    assert len(client.queries) == 1
    assert 'metrics.search_budget_lost_impression_share' in client.queries[0]
