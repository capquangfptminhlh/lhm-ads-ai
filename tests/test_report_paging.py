"""Meta/Google report completeness tests: no Ads mutations, no arbitrary paging URLs."""
import asyncio

import pytest
from fastapi import HTTPException

from ads_core import optimizations,goals

META={'org_id':'org-one','id':17,'platform':'meta','external_id':'act_1234567890',
      'currency':'USD','token_ciphertext':'ENCRYPTED'}
GOOGLE={'org_id':'org-one','id':17,'platform':'google','external_id':'9876543210',
        'currency':'USD','token_ciphertext':'ENCRYPTED'}


class Reply:
    def __init__(self,body,code=200):
        self.body=body
        self.status_code=code
    def json(self):
        return self.body
    def raise_for_status(self):
        if self.status_code>=400:
            raise ValueError('Mock provider HTTP rejection')


class PagedMeta:
    def __init__(self):
        self.calls=[]
    async def get(self,url,**kwargs):
        self.calls.append((url,dict(kwargs.get('params') or {})))
        p=kwargs['params']
        if url.endswith('/campaigns'):
            if not p.get('after'):
                return Reply({'data':[{'id':'12345678901','name':'First','status':'ACTIVE'}],
                    'paging':{'next':'https://evil.example/steal-token',
                              'cursors':{'after':'CAMPAIGN-2'}}})
            assert p['after']=='CAMPAIGN-2'
            return Reply({'data':[{'id':'12345678902','name':'Second','status':'ACTIVE'}]})
        if url.endswith('/insights'):
            if not p.get('after'):
                return Reply({'data':[{'campaign_id':'12345678901','spend':'100','clicks':'110',
                                      'impressions':'1000','account_currency':'USD',
                                      'actions':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'5'}],
                                      'action_values':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'500'}]}],
                    'paging':{'next':'https://evil.example/steal-token',
                              'cursors':{'after':'INSIGHT-2'}}})
            assert p['after']=='INSIGHT-2'
            return Reply({'data':[{'campaign_id':'12345678902','spend':'70','clicks':'105',
                                  'impressions':'900','account_currency':'USD',
                                  'actions':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'7'}],
                                  'action_values':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'280'}]}]})
        if url.endswith('/adsets'):
            return Reply({'data':[]})
        raise AssertionError('Unexpected provider address')
    async def post(self,*args,**kwargs):
        raise AssertionError('No Ads write permitted')


def test_meta_two_page_campaigns_and_insights_do_not_follow_next_url(monkeypatch):
    monkeypatch.setattr(optimizations,'account_token',lambda _: 'FAKE')
    monkeypatch.setattr(goals,'goal_for',lambda org,aid:{
        'enabled':1,'meta_action_type':'offsite_conversion.fb_pixel_purchase'})
    provider=PagedMeta()
    campaigns=asyncio.run(optimizations.meta_campaigns(META,provider))
    assert [x['id'] for x in campaigns]==['12345678901','12345678902']
    assert [x['cpa'] for x in campaigns]==[20.0,10.0]
    assert [x['roas'] for x in campaigns]==[5.0,4.0]
    assert len(provider.calls)==5
    assert all('evil.example' not in url for url,_ in provider.calls)
    assert [p.get('after') for _,p in provider.calls]==[
        None,'CAMPAIGN-2',None,'INSIGHT-2',None]


def test_pagination_cursor_missing_repeated_or_overflow():
    async def check(behaviour):
        class Client:
            calls=0
            async def get(self,url,**kwargs):
                self.calls+=1
                return Reply(behaviour(self.calls,kwargs['params']))
        return await optimizations._meta_pages(
            Client(),'https://graph.facebook.com/v24.0/act_123/campaigns',
            {'Authorization':'Bearer FAKE'},{'limit':100})

    def missing(n,p):
        return {'data':[],'paging':{'next':'https://example.org/untrusted'}}
    with pytest.raises(ValueError):
        asyncio.run(check(missing))

    def repeat(n,p):
        return {'data':[],'paging':{'next':'https://example.org/untrusted',
                                  'cursors':{'after':'unchanged'}}}
    with pytest.raises(ValueError):
        asyncio.run(check(repeat))

    def overflow(n,p):
        return {'data':[{'id':str(i)} for i in range(501)]}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(check(overflow))
    assert exc.value.status_code==409


def test_insights_error_fails_entire_scan(monkeypatch):
    monkeypatch.setattr(optimizations,'account_token',lambda _: 'FAKE')
    monkeypatch.setattr(goals,'goal_for',lambda org,aid:None)
    class Provider:
        async def get(self,url,**kwargs):
            if url.endswith('/campaigns'):
                return Reply({'data':[{'id':'12345678901','name':'Active','status':'ACTIVE'}]})
            return Reply({'error':'rate-limited'},code=429)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(optimizations.meta_campaigns(META,Provider()))
    assert exc.value.status_code==502


def test_google_large_account_does_not_silently_report_first_100(monkeypatch):
    async def fake_access(client,acc):
        return ('9876543210','v25',{'Authorization':'Bearer FAKE'})
    monkeypatch.setattr(optimizations,'google_access',fake_access)
    class Provider:
        async def post(self,url,**kwargs):
            assert 'LIMIT 501' in kwargs['json']['query']
            pages=[{'campaign':{'id':str(1000000000+i),'name':'Name','status':'ENABLED'},
                    'metrics':{'costMicros':'1000000','clicks':'10','impressions':'100'}} for i in range(501)]
            return Reply([{'results':pages}])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(optimizations.google_campaigns(GOOGLE,Provider()))
    assert exc.value.status_code==409
