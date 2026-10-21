"""Real Meta Insights read API, safe Meta pause operation; unmistakable demo fixtures."""
import os
import json
import re
from datetime import date, timedelta
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from .security import unseal

META_VERSION = lambda: os.getenv('META_GRAPH_VERSION', 'v24.0')
META_HOST = 'https://graph.facebook.com'


def account_token(acc):
    cipher = acc['token_ciphertext']
    if not cipher:
        raise HTTPException(422, 'Tài khoản chưa kết nối API hợp lệ')
    return unseal(cipher, f"acct:{acc['org_id']}:{acc['platform']}:{acc['external_id']}")


def demo_report(account_id, period):
    # Deterministic example data; never report demo as real ads performance.
    factor = 1 if period == 'yesterday' else 7
    seed = int(account_id)
    rows = []
    n = 1 if factor == 1 else 7
    for i in range(n):
        spend = (310_000 + (seed * 41_000 + i * 29_000) % 270_000)
        impressions = 8900 + (seed * 1700 + i * 913) % 9200
        clicks = 110 + (seed * 37 + i * 13) % 190
        rows.append({'date': (date.today() - timedelta(days=n-i)).isoformat(),
                     'spend': spend, 'impressions': impressions, 'clicks': clicks})
    return report_output(rows, 'VND', 'demo')


def report_output(rows, currency, source):
    spend = round(sum(float(x.get('spend') or 0) for x in rows), 2)
    impressions = sum(int(x.get('impressions') or 0) for x in rows)
    clicks = sum(int(x.get('clicks') or 0) for x in rows)
    # Only expose conversion KPIs when the provider actually supplied them.
    # Google reports include conversion counts/values, while the generic Meta
    # account Insights summary does not declare a goal/action definition.
    has_conversions=bool(rows) and all(x.get('conversions') is not None for x in rows)
    has_values=bool(rows) and all(x.get('conversion_value') is not None for x in rows)
    conversions=round(sum(float(x['conversions']) for x in rows),2) if has_conversions else None
    conversion_value=round(sum(float(x['conversion_value']) for x in rows),2) if has_values else None
    return {'source': source, 'currency': currency, 'spend': spend,
            'impressions': impressions, 'clicks': clicks,
            'ctr': round(clicks * 100 / impressions, 2) if impressions else 0,
            'cpc': round(spend / clicks, 2) if clicks else None,
            'conversions':conversions,'conversion_value':conversion_value,
            'conversion_action_type':'google_all_conversions' if source=='google_live' and has_conversions else None,
            'cpa':round(spend/conversions,2) if conversions and conversions>0 else None,
            'roas':round(conversion_value/spend,2) if conversion_value is not None and spend>0 else None,
            'daily': rows}


async def fetch_report(acc, period='last_7d'):
    if period not in ('last_7d', 'yesterday'):
        raise HTTPException(422, 'Khoảng thời gian không hỗ trợ')
    if acc['platform'] == 'demo':
        return demo_report(acc['id'], period)
    if acc['platform'] == 'google':
        return await google_report(acc,period)
    if acc['platform'] != 'meta':
        raise HTTPException(501, f"{acc['platform'].upper()}: adapter báo cáo đang phát triển, không trả dữ liệu giả")
    external = acc['external_id'].replace('act_', '')
    if not re.fullmatch(r'\d{4,30}', external):
        raise HTTPException(422, 'ID tài khoản Meta không hợp lệ')
    token = account_token(acc)
    preset = 'yesterday' if period == 'yesterday' else 'last_7d'
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f'{META_HOST}/{META_VERSION()}/act_{external}/insights',
                headers={'Authorization': f'Bearer {token}'},
                params={'fields':'date_start,spend,impressions,clicks',
                        'date_preset':preset,'time_increment':1,'limit':31})
            r.raise_for_status()
            data = r.json()
            if 'error' in data:
                raise ValueError('Meta API trả về lỗi')
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'Không lấy được số liệu Meta: kiểm tra token, quyền ads_read và ID tài khoản')
    rows = [{'date':x.get('date_start'), 'spend':float(x.get('spend',0)),
             'impressions':int(x.get('impressions',0)), 'clicks':int(x.get('clicks',0))}
            for x in data.get('data', [])]
    return report_output(rows, acc['currency'], 'meta_live')


async def pause_meta_campaign(acc, campaign_id):
    if acc['platform'] != 'meta':
        raise HTTPException(422, 'MVP chỉ cho phép tạm dừng chiến dịch Meta')
    if not re.fullmatch(r'\d{5,30}', campaign_id):
        raise HTTPException(422, 'ID chiến dịch không hợp lệ')
    token = account_token(acc)
    acc_id = acc['external_id'].replace('act_', '')
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            check = await client.get(f'{META_HOST}/{META_VERSION()}/{campaign_id}',
                headers={'Authorization': f'Bearer {token}'},
                params={'fields':'id,account_id'})
            check.raise_for_status()
            body = check.json()
            if str(body.get('account_id','')).replace('act_', '') != acc_id:
                raise HTTPException(403,'Chiến dịch không thuộc tài khoản đã chọn')
            response = await client.post(f'{META_HOST}/{META_VERSION()}/{campaign_id}',
                headers={'Authorization': f'Bearer {token}'},data={'status':'PAUSED'})
            response.raise_for_status()
            if response.json().get('success') is not True:
                raise HTTPException(502,'Meta chưa xác nhận đã tạm dừng chiến dịch')
    except httpx.HTTPError:
        raise HTTPException(502,'Meta API từ chối thao tác: kiểm tra ads_management và quyền tài khoản')
    except ValueError:
        raise HTTPException(502,'Meta API trả về dữ liệu không hợp lệ')
    return {'success':True}


async def google_report(acc, period):
    """Google Ads v25 read-only GAQL; untested against a customer's live credentials.
    Account token is a JSON credential bundle, encrypted like other providers.
    """
    account_id=acc['external_id'].replace('-', '')
    if not re.fullmatch(r'\d{8,20}',account_id):
        raise HTTPException(422,'Google Ads customer ID phải là số')
    # Google Ads API auth is associated with Google Cloud project since 2026; legacy dev token optional.
    developer_token=os.environ.get('GOOGLE_ADS_DEVELOPER_TOKEN','')
    try:
        credentials=json.loads(account_token(acc))
        if not all(isinstance(credentials.get(field),str) and credentials[field] for field in ('client_id','refresh_token')):
            raise ValueError('Missing OAuth credentials')
    except (json.JSONDecodeError,ValueError,TypeError):
        raise HTTPException(422,'Google Ads token phải là JSON gồm client_id và refresh_token (client_secret có thể để trống ở Desktop)')
    during='YESTERDAY' if period=='yesterday' else 'LAST_7_DAYS'
    query=('SELECT segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks, '
           'metrics.conversions, metrics.conversions_value '
           f'FROM customer WHERE segments.date DURING {during} ORDER BY segments.date ASC')
    headers={}
    if developer_token: headers['developer-token']=developer_token
    if credentials.get('login_customer_id'):
        login_customer_id=credentials['login_customer_id'].replace('-', '')
        if not re.fullmatch(r'\d{8,20}',login_customer_id):
            raise HTTPException(422,'Google Ads login_customer_id không hợp lệ')
        headers['login-customer-id']=login_customer_id
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            oauth=await client.post('https://oauth2.googleapis.com/token',data={
                **({'client_secret': credentials['client_secret']} if credentials.get('client_secret') else {}),
                'client_id':credentials['client_id'],
                'refresh_token':credentials['refresh_token'],'grant_type':'refresh_token'})
            oauth.raise_for_status()
            access_token=oauth.json().get('access_token')
            if not access_token:raise ValueError('No access token')
            headers['Authorization']='Bearer '+access_token
            response=await client.post('https://googleads.googleapis.com/v25/customers/'+account_id+'/googleAds:searchStream',
                                       headers=headers,json={'query':query})
            response.raise_for_status()
            results=response.json()
    except (httpx.HTTPError,ValueError,TypeError):
        raise HTTPException(502,'Không lấy được Google Ads: kiểm tra OAuth, quyền API của Google Cloud và customer ID')
    if not isinstance(results,list):
        raise HTTPException(502,'Google Ads trả về dữ liệu không hợp lệ')
    days={}
    for page in results:
        for item in page.get('results',[]):
            ds=item.get('segments',{}).get('date')
            if not ds:continue
            metrics=item.get('metrics',{})
            x=days.setdefault(ds,{'date':ds,'spend':0.0,'impressions':0,'clicks':0})
            x['spend']+=int(metrics.get('costMicros') or 0)/1_000_000
            x['impressions']+=int(metrics.get('impressions') or 0)
            x['clicks']+=int(metrics.get('clicks') or 0)
            # Missing values are unknown (not silently assumed to be zero).
            for source_key,dest in (('conversions','conversions'),('conversionsValue','conversion_value')):
                if source_key in metrics and metrics[source_key] is not None:
                    x[dest]=float(x.get(dest,0) or 0)+float(metrics[source_key])
    return report_output([days[k] for k in sorted(days)],acc['currency'],'google_live')
