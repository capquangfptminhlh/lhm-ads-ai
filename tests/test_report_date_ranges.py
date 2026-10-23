"""Calendar range correctness across UI, API, Google GAQL, Meta and Demo."""
import asyncio
import json
from datetime import date
from pathlib import Path
import pytest
from fastapi import HTTPException

from ads_core.report_dates import resolve_date_range, PERIODS
from ads_core import providers

NOW=date(2026, 10, 23)

@pytest.mark.parametrize('period,first,last',[
 ('today','2026-10-23','2026-10-23'),
 ('yesterday','2026-10-22','2026-10-22'),
 ('last_7d','2026-10-17','2026-10-23'),
 ('last_14d','2026-10-10','2026-10-23'),
 ('last_30d','2026-09-24','2026-10-23'),
 ('last_90d','2026-07-26','2026-10-23'),
 ('this_week','2026-10-19','2026-10-23'),
 ('last_week','2026-10-12','2026-10-18'),
 ('this_month','2026-10-01','2026-10-23'),
 ('last_month','2026-09-01','2026-09-30'),
 ('this_quarter','2026-10-01','2026-10-23'),
 ('last_quarter','2026-07-01','2026-09-30'),
 ('this_year','2026-01-01','2026-10-23'),
 ('last_year','2025-01-01','2025-12-31'),
])
def test_presets(period,first,last):
    assert resolve_date_range(period,today=NOW)==(first,last)

@pytest.mark.parametrize('args',[
 ('custom',None,None),('custom','2026-10-22',None),
 ('custom','2026-10-24','2026-10-24'),
 ('custom','2026-10-23','2026-10-22'),
 ('custom','2025-09-01','2026-10-23'),
 ('custom',"2026-10-01' OR 1=1 --",'2026-10-23'),
 ('custom','2026-02-30','2026-10-23'),
 ('custom','2026-10-20T00:00','2026-10-23'),
 ('today','2026-10-01','2026-10-23'),
 ('made_up',None,None),
])
def test_invalid_range_fails_closed(args):
    with pytest.raises(HTTPException) as exc:
        resolve_date_range(*args,today=NOW)
    assert exc.value.status_code==422

def test_custom_and_leap_year():
    assert resolve_date_range('custom','2026-10-18','2026-10-23',today=NOW)==('2026-10-18','2026-10-23')
    assert resolve_date_range('last_year',today=date(2025,2,3))==('2024-01-01','2024-12-31')

def test_demo_range_never_masquerades_as_live():
    demo=providers.demo_report(5,'custom','2026-10-20','2026-10-23')
    assert demo['source']=='demo'
    assert len(demo['daily'])==4
    assert demo['daily'][0]['date']=='2026-10-20'
    assert demo['daily'][-1]['date']=='2026-10-23'

def test_both_providers_receive_exact_validated_dates(monkeypatch):
    calls=[]
    account={'id':1,'org_id':'org','platform':'google','external_id':'1234567890','currency':'VND'}
    google_creds=json.dumps({'client_id':'some-client','refresh_token':'some-refresh'})
    monkeypatch.setattr(providers,'account_token',lambda acc:google_creds if acc['platform']=='google' else 'safe-token')
    class Reply:
        def __init__(self,data):self.data=data
        def raise_for_status(self):pass
        def json(self):return self.data
    class Client:
        def __init__(self,*a,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):return False
        async def post(self,url,**kw):
            calls.append(('POST',url,kw))
            if url.endswith('/token'):return Reply({'access_token':'fake'})
            return Reply([{'results':[{'segments':{'date':'2026-10-21'},'metrics':{'clicks':17,'costMicros':'1000000','impressions':200}}]}])
        async def get(self,url,**kw):
            calls.append(('GET',url,kw))
            return Reply({'data':[{'date_start':'2026-10-21','spend':'1','clicks':'2','impressions':'20'}]})
    monkeypatch.setattr(providers.httpx,'AsyncClient',Client)
    g=asyncio.run(providers.fetch_report(account,'custom','2026-10-20','2026-10-23'))
    assert g['source']=='google_live'
    query=next(kw['json']['query'] for method,url,kw in calls if 'searchStream' in url)
    assert "segments.date BETWEEN '2026-10-20' AND '2026-10-23'" in query
    account['platform']='meta';account['external_id']='act_1234567890'
    m=asyncio.run(providers.fetch_report(account,'custom','2026-10-20','2026-10-23'))
    assert m['source']=='meta_live'
    params=next(kw['params'] for method,url,kw in calls if 'insights' in url)
    assert json.loads(params['time_range'])=={'since':'2026-10-20','until':'2026-10-23'}
    assert 'date_preset' not in params

def test_customer_date_selection_is_end_to_end_not_only_options():
    static=Path(__file__).resolve().parents[1]/'static'
    page=(static/'studio.html').read_text(encoding='utf-8')
    script=(static/'report-date-ranges.js').read_text(encoding='utf-8')
    dashboard=(static/'studio.js').read_text(encoding='utf-8')
    reports=(static/'workspace-pages.js').read_text(encoding='utf-8')
    app=(static.parent/'ads_core'/'app.py').read_text(encoding='utf-8')
    extended=(static.parent/'ads_core'/'extended.py').read_text(encoding='utf-8')
    for p in PERIODS:
        assert page.count('value="'+p+'"')>=2
    assert 'id="dashboard-custom-dates"' in page
    assert 'id="report-custom-dates"' in page
    assert '/static/report-date-ranges.js' in page
    assert '/static/report-date-ranges.css' in page
    assert "q.set('date_from'" in script and "q.set('date_to'" in script
    assert "ensureReady('period')" in dashboard
    assert "ensureReady('ws-report-period')" in reports
    assert "date_from:str|None=None" in app
    assert "date_from=date_from,date_to=date_to" in extended
    assert "period='custom'" not in script
