"""Offline Meta Insights event normalization: one action, exact attribution, no Ads writes."""
import asyncio

from ads_core import goals, optimizations


ACCOUNT={'org_id':'tenant-a','id':8,'platform':'meta','external_id':'act_1234567890',
         'currency':'USD','token_ciphertext':'ENCRYPTED'}
CAMPAIGN={'id':'12345678901','name':'Campaign','status':'ACTIVE','effective_status':'ACTIVE'}
PURCHASE='offsite_conversion.fb_pixel_purchase'


class FakeResponse:
    status_code=200
    def __init__(self,payload):self.payload=payload
    def json(self):return self.payload
    def raise_for_status(self):pass


class MetaAPI:
    def __init__(self,row):
        self.row=row
        self.requests=[]
    async def get(self,url,**kw):
        self.requests.append((url,kw))
        if url.endswith('/campaigns'):
            return FakeResponse({'data':[CAMPAIGN]})
        if url.endswith('/insights'):
            return FakeResponse({'data':[self.row]})
        raise AssertionError('No other HTTP allowed')
    async def post(self,*args,**kwargs):
        raise AssertionError('Read-only campaign insights must never modify Ads')


def row(actions,values=None,currency='USD'):
    return {'campaign_id':CAMPAIGN['id'],'spend':'120','clicks':'150','impressions':'3000',
            'account_currency':currency,'actions':actions,'action_values':values}


def run_meta(monkeypatch,raw,action=PURCHASE):
    monkeypatch.setattr(optimizations,'account_token',lambda acc:'MOCK_TOKEN')
    monkeypatch.setattr(goals,'goal_for',lambda org,aid:{'enabled':1,'meta_action_type':action})
    client=MetaAPI(raw)
    campaigns=asyncio.run(optimizations.meta_campaigns(ACCOUNT,client))
    assert all('/insights' in url or '/campaigns' in url for url,_ in client.requests)
    p=client.requests[1][1]['params']
    assert p['action_attribution_windows']=='["7d_click"]'
    assert p['action_report_time']=='conversion'
    assert 'actions' in p['fields'] and 'action_values' in p['fields']
    return campaigns[0]


def test_purchase_one_event_not_sum_across_actions(monkeypatch):
    data=row(
        [{'action_type':'offsite_conversion.fb_pixel_lead','value':'100'},
         {'action_type':PURCHASE,'7d_click':'8','value':'11'}],
        [{'action_type':PURCHASE,'7d_click':'420','value':'500'}])
    result=run_meta(monkeypatch,data)
    assert result['conversions']==8
    assert result['conversion_value']==420
    assert result['cpa']==15
    assert result['roas']==3.5
    assert result['conversion_action_type']==PURCHASE
    assert result['conversion_source']=='meta_actions_7d_click'
    goal={'enabled':1,'meta_action_type':PURCHASE,'objective':'roas','target':5,
          'min_conversions':5,'min_clicks':100,'currency':'USD'}
    advice=goals.evaluate_goals([result],'meta','USD',goal)
    assert len(advice)==1 and advice[0]['code']=='roas_below_goal'


def test_missing_purchase_value_is_not_zero_roas(monkeypatch):
    result=run_meta(monkeypatch,row(
        [{'action_type':PURCHASE,'value':'6'}],[]))
    assert result['conversions']==6
    assert result['cpa']==20
    assert result['conversion_value'] is None
    assert result['roas'] is None
    goal={'enabled':1,'meta_action_type':PURCHASE,'objective':'roas','target':2,
          'min_conversions':5,'min_clicks':100,'currency':'USD'}
    assert goals.evaluate_goals([result],'meta','USD',goal)==[]


def test_missing_action_wrong_currency_and_duplicate_are_unknown(monkeypatch):
    lead=[{'action_type':'offsite_conversion.fb_pixel_lead','value':'7'}]
    missing=run_meta(monkeypatch,row(lead),PURCHASE)
    assert missing['conversions'] is None and missing['cpa'] is None
    wrong=run_meta(monkeypatch,row([{'action_type':PURCHASE,'value':'8'}],currency='EUR'))
    assert wrong['conversions'] is None and wrong['roas'] is None
    duplicate=run_meta(monkeypatch,row(
        [{'action_type':PURCHASE,'value':'8'},{'action_type':PURCHASE,'value':'5'}]))
    assert duplicate['conversions'] is None
    assert optimizations._meta_action_number([{'action_type':PURCHASE,'value':'NaN'}],PURCHASE) is None
    assert optimizations._meta_action_number([{'action_type':PURCHASE,'value':'-2'}],PURCHASE) is None
    assert optimizations._meta_action_number([{'action_type':PURCHASE,'value':'4.2'}],PURCHASE)==4.2


def test_meta_lead_cpa_and_scope_not_purchase(monkeypatch):
    action='offsite_conversion.fb_pixel_lead'
    result=run_meta(monkeypatch,row([{'action_type':action,'value':'9'}]),action)
    assert result['conversions']==9 and result['cpa']==round(120/9,2)
    assert result['conversion_value'] is None and result['roas'] is None
    goal={'enabled':1,'meta_action_type':action,'objective':'cpa','target':9,
          'min_conversions':5,'min_clicks':100,'currency':'USD'}
    assert goals.evaluate_goals([result],'meta','USD',goal)[0]['code']=='cpa_above_goal'
    goal['meta_action_type']=PURCHASE
    assert goals.evaluate_goals([result],'meta','USD',goal)==[]
    result['effective_status']='PAUSED'
    goal['meta_action_type']=action
    assert goals.evaluate_goals([result],'meta','USD',goal)==[]
