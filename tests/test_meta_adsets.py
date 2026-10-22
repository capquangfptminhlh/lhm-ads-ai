"""Meta ad-set bid targets: median bid_amount per campaign (minor units),
campaign-level precedence, fail-closed ad-set fetch. Offline fakes only:
no external writes or customer access."""
import asyncio

import httpx
import pytest
from fastapi import HTTPException

from ads_core import goals, optimizations


ACCOUNT={'org_id':'tenant-a','id':8,'platform':'meta','external_id':'act_1234567890',
         'currency':'USD','token_ciphertext':'ENCRYPTED'}
CAMPAIGN={'id':'12345678901','name':'Campaign','status':'ACTIVE','effective_status':'ACTIVE'}
CAMPAIGN2={'id':'12345678902','name':'Second','status':'ACTIVE','effective_status':'ACTIVE'}


class FakeResponse:
    status_code=200
    def __init__(self,payload):self.payload=payload
    def json(self):return self.payload
    def raise_for_status(self):pass


class MetaAPI:
    """Fake Graph client. `adsets` may be a list of rows, a raw page payload
    dict, or an exception instance to raise from the /adsets request."""
    def __init__(self,adsets,campaigns=None):
        self.adsets=adsets
        self.campaigns=[CAMPAIGN] if campaigns is None else campaigns
        self.requests=[]
    async def get(self,url,**kw):
        self.requests.append((url,kw))
        if url.endswith('/campaigns'):
            return FakeResponse({'data':self.campaigns})
        if url.endswith('/insights'):
            return FakeResponse({'data':[]})
        if url.endswith('/adsets'):
            if isinstance(self.adsets,Exception):
                raise self.adsets
            if isinstance(self.adsets,dict):
                return FakeResponse(self.adsets)
            return FakeResponse({'data':self.adsets})
        raise AssertionError('No other HTTP allowed')
    async def post(self,*args,**kwargs):
        raise AssertionError('Read-only ad-set reads must never modify Ads')


def adset(cid,amount_marker='absent',adset_id='555000111'):
    row={'id':adset_id,'campaign_id':cid,'bid_strategy':'LOWEST_COST_WITH_BID_CAP'}
    if amount_marker!='absent':
        row['bid_amount']=amount_marker
    return row


def run_meta(monkeypatch,adsets,campaigns=None):
    monkeypatch.setattr(optimizations,'account_token',lambda acc:'MOCK_TOKEN')
    monkeypatch.setattr(goals,'goal_for',lambda org,aid:None)
    client=MetaAPI(adsets,campaigns)
    result=asyncio.run(optimizations.meta_campaigns(ACCOUNT,client))
    return result,client


def test_median_odd_count_and_minor_unit_conversion(monkeypatch):
    # Graph sends bid_amount as minor-unit strings: 1000 -> 10.00 USD.
    rows=[adset(CAMPAIGN['id'],'1000','1'),adset(CAMPAIGN['id'],'3000','2'),
          adset(CAMPAIGN['id'],'2000','3')]
    campaigns,client=run_meta(monkeypatch,rows)
    assert campaigns[0]['adset_bid_target_cpa']==20.0  # median of 10, 30, 20
    adset_calls=[kw for url,kw in client.requests if url.endswith('/adsets')]
    assert len(adset_calls)==1
    fields=adset_calls[0]['params']['fields']
    assert fields=='id,campaign_id,bid_strategy,bid_amount'


def test_median_even_count_averages_middle_pair(monkeypatch):
    rows=[adset(CAMPAIGN['id'],1000,'1'),adset(CAMPAIGN['id'],2000,'2'),
          adset(CAMPAIGN['id'],3000,'3'),adset(CAMPAIGN['id'],5000,'4')]
    campaigns,_=run_meta(monkeypatch,rows)
    assert campaigns[0]['adset_bid_target_cpa']==25.0  # median of 10, 20, 30, 50


def test_missing_or_unusable_bid_amount_stays_none(monkeypatch):
    rows=[adset(CAMPAIGN['id']),                       # no bid_amount key at all
          adset(CAMPAIGN['id'],None,'2'),              # explicit null
          adset(CAMPAIGN['id'],'not-a-number','3'),     # non-numeric
          adset(CAMPAIGN['id'],'-500','4'),            # negative is not a target
          adset('99999999999','7000','5')]             # unknown campaign: ignored
    campaigns,_=run_meta(monkeypatch,rows,campaigns=[CAMPAIGN,CAMPAIGN2])
    assert campaigns[0]['adset_bid_target_cpa'] is None
    assert campaigns[1]['adset_bid_target_cpa'] is None  # key present on every campaign


def test_median_is_per_campaign_not_account_wide(monkeypatch):
    rows=[adset(CAMPAIGN['id'],'1000','1'),
          adset(CAMPAIGN2['id'],'9000','2'),adset(CAMPAIGN2['id'],'11000','3')]
    campaigns,_=run_meta(monkeypatch,rows,campaigns=[CAMPAIGN,CAMPAIGN2])
    assert campaigns[0]['adset_bid_target_cpa']==10.0
    assert campaigns[1]['adset_bid_target_cpa']==100.0  # median of 90, 110


def test_campaign_level_target_wins_over_adset_median():
    found=[{'id':CAMPAIGN['id'],'bid_target_cpa':42.0,'adset_bid_target_cpa':None}]
    optimizations._apply_adset_bid_targets(found,[adset(CAMPAIGN['id'],'99900')])
    assert found[0]['adset_bid_target_cpa'] is None  # campaign value wins; ad-set value not attached
    bare=[{'id':CAMPAIGN['id'],'bid_target_cpa':None,'adset_bid_target_cpa':None}]
    optimizations._apply_adset_bid_targets(bare,[adset(CAMPAIGN['id'],'99900')])
    assert bare[0]['adset_bid_target_cpa']==999.0


def test_adset_transport_error_fails_whole_call_with_502(monkeypatch):
    monkeypatch.setattr(optimizations,'account_token',lambda acc:'MOCK_TOKEN')
    monkeypatch.setattr(goals,'goal_for',lambda org,aid:None)
    boom=httpx.ConnectError('connection reset',request=httpx.Request('GET','https://graph.facebook.com'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(optimizations.meta_campaigns(ACCOUNT,MetaAPI(boom)))
    assert exc.value.status_code==502


def test_adset_malformed_page_fails_whole_call_with_502(monkeypatch):
    monkeypatch.setattr(optimizations,'account_token',lambda acc:'MOCK_TOKEN')
    monkeypatch.setattr(goals,'goal_for',lambda org,aid:None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(optimizations.meta_campaigns(ACCOUNT,MetaAPI({'data':'not-a-list'})))
    assert exc.value.status_code==502
