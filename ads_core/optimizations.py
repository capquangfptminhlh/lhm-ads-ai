"""Account-scoped campaign reporting and conservative advisory rules.

No LLM ever holds provider credentials or can invoke ad-writing functions.
Inspections only use first-party Ads APIs; campaign names stay on the local PC.
"""
from __future__ import annotations

import json
import os
import re
import math

import httpx
from fastapi import Depends, HTTPException

from .app import app, get_account, require
from .providers import account_token

ID = re.compile(r'\d{5,30}\Z')
GOOGLE_CUSTOMER = re.compile(r'\d{8,20}\Z')
MAX_CAMPAIGNS = 500
META_PAGE_SIZE = 100
META_MAX_PAGES = 6  # A sixth page is only allowed to detect overflow.


def _google_headers(credential, access_token):
    headers = {'Authorization': 'Bearer ' + access_token}
    developer = os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN', '').strip()
    if developer:
        headers['developer-token'] = developer
    manager = str(credential.get('login_customer_id') or '').replace('-', '')
    if manager:
        if not GOOGLE_CUSTOMER.fullmatch(manager):
            raise HTTPException(422, 'Google manager ID không hợp lệ')
        headers['login-customer-id'] = manager
    return headers


async def google_access(client, acc):
    account_id = str(acc['external_id']).replace('-', '')
    if not GOOGLE_CUSTOMER.fullmatch(account_id):
        raise HTTPException(422, 'Google customer ID không hợp lệ')
    try:
        bundle = json.loads(account_token(acc))
        if not isinstance(bundle, dict) or not all(bundle.get(k) for k in ('client_id', 'refresh_token')):
            raise ValueError('Invalid local OAuth bundle')
        data = {'client_id': bundle['client_id'], 'refresh_token': bundle['refresh_token'],
                'grant_type': 'refresh_token'}
        if bundle.get('client_secret'):
            data['client_secret'] = bundle['client_secret']
        response = await client.post('https://oauth2.googleapis.com/token', data=data)
        response.raise_for_status()
        access = response.json().get('access_token')
        if not isinstance(access, str) or not access:
            raise ValueError('No access token')
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, httpx.HTTPError):
        raise HTTPException(502, 'Không lấy được Google OAuth access token.') from None
    version = os.getenv('GOOGLE_ADS_API_VERSION', 'v25')
    if not re.fullmatch(r'v\d+', version):
        raise HTTPException(503, 'Google Ads API version không hợp lệ')
    return account_id, version, _google_headers(bundle, access)


async def google_campaigns(acc, client):
    customer, version, headers = await google_access(client, acc)
    # No date dimension here: one aggregate metric row per campaign over 7 days.
    query = ("SELECT campaign.id, campaign.name, campaign.status, "
             "metrics.cost_micros, metrics.impressions, metrics.clicks, "
             "metrics.conversions, metrics.conversions_value "
             "FROM campaign WHERE campaign.status != REMOVED "
             "AND segments.date DURING LAST_7_DAYS LIMIT 501")
    try:
        response = await client.post(
            f'https://googleads.googleapis.com/{version}/customers/{customer}/googleAds:searchStream',
            headers=headers, json={'query': query})
        response.raise_for_status()
        pages = response.json()
        if not isinstance(pages, list):
            raise ValueError('Invalid campaign response')
        found = []
        for page in pages:
            for entry in page.get('results', []):
                item = entry.get('campaign') or {}
                cid = str(item.get('id', ''))
                if not ID.fullmatch(cid):
                    continue
                metrics = entry.get('metrics') or {}
                spend = int(metrics.get('costMicros') or 0)/1_000_000
                conversions = float(metrics.get('conversions') or 0)
                value = float(metrics.get('conversionsValue') or 0)
                clicks = int(metrics.get('clicks') or 0)
                impressions = int(metrics.get('impressions') or 0)
                found.append({
                    'id': cid, 'name': str(item.get('name') or 'Google Campaign')[:100],
                    'status': str(item.get('status') or 'UNKNOWN'),
                    'spend': round(spend, 2), 'clicks': clicks, 'impressions': impressions,
                    'conversions': round(conversions, 2), 'conversion_value': round(value, 2),
                    'ctr_percent': round(clicks*100/impressions, 2) if impressions else None,
                    'cpa': round(spend/conversions, 2) if conversions>0 else None,
                    'roas': round(value/spend, 3) if spend>0 else None,
                })
                if len(found) > MAX_CAMPAIGNS:
                    raise HTTPException(409, 'Quá 500 chiến dịch; không thể kiểm tra đầy đủ và tạo cảnh báo an toàn.')
        return found
    except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError):
        raise HTTPException(502, 'Không đọc được chiến dịch Google Ads; kiểm tra quyền API.') from None


def _meta_action_number(rows, action_type):
    """Return exactly one event's value; absent or ambiguous is not zero."""
    if not isinstance(rows,list):
        return None
    matches=[r for r in rows if isinstance(r,dict) and r.get('action_type')==action_type]
    if len(matches)!=1:
        return None
    try:
        raw=matches[0].get('7d_click',matches[0].get('value'))
        if raw is None or isinstance(raw,bool):
            return None
        value=float(raw)
        return value if math.isfinite(value) and value>=0 else None
    except (TypeError,ValueError,OverflowError):
        return None


async def _meta_pages(client, url, headers, params):
    """Bounded Meta cursor pagination; never follow arbitrary paging.next URL.

    Fails closed on truncation, repeated cursor, malformed JSON and HTTP errors.
    No write API is called. This prevents falsely resolving existing alerts when
    only one partial page of campaign/insight data was returned.
    """
    collected = []
    seen = set()
    args = dict(params)
    for _ in range(META_MAX_PAGES):
        response = await client.get(url, headers=headers, params=args)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get('data'), list):
            raise ValueError('Invalid Meta Graph page')
        collected.extend(body['data'])
        if len(collected) > MAX_CAMPAIGNS:
            raise HTTPException(409, 'Meta có trên 500 dòng dữ liệu: quét chưa đầy đủ; không đưa ra kết luận.')
        paging = body.get('paging') or {}
        if not isinstance(paging, dict):
            raise ValueError('Invalid Graph paging')
        if not paging.get('next'):
            return collected
        cursors = paging.get('cursors') or {}
        if not isinstance(cursors, dict):
            raise ValueError('Invalid Graph cursors')
        cursor = cursors.get('after')
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 1024:
            raise ValueError('Missing Meta cursor')
        if cursor in seen:
            raise ValueError('Repeated Meta cursor')
        seen.add(cursor)
        args['after'] = cursor  # Same trusted endpoint; never fetch paging.next.
    raise HTTPException(409, 'Dữ liệu Meta phân trang vượt ngưỡng an toàn.')


async def meta_campaigns(acc, client):
    aid = str(acc['external_id']).removeprefix('act_')
    if not re.fullmatch(r'\d{4,30}', aid):
        raise HTTPException(422, 'Meta account ID không hợp lệ')
    version = os.getenv('META_GRAPH_VERSION', 'v24.0')
    if not re.fullmatch(r'v\d+\.\d+', version):
        raise HTTPException(503, 'Meta Graph version không hợp lệ')
    headers = {'Authorization': 'Bearer ' + account_token(acc)}
    base = f'https://graph.facebook.com/{version}/act_{aid}'
    from .goals import goal_for
    goal=goal_for(acc['org_id'],acc['id'])
    chosen_action=goal.get('meta_action_type') if goal and goal['enabled'] else None
    try:
        entries = await _meta_pages(client, base + '/campaigns', headers,
                                    {'fields': 'id,name,status,effective_status',
                                     'limit': META_PAGE_SIZE})
        found = []
        known_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Invalid campaign row')
            cid = str(entry.get('id', ''))
            if not ID.fullmatch(cid):
                continue
            if cid in known_ids:
                raise ValueError('Duplicate campaign')
            known_ids.add(cid)
            found.append({'id': cid, 'name': str(entry.get('name') or 'Meta Campaign')[:100],
                          'status': str(entry.get('status') or 'UNKNOWN'),
                          'effective_status': str(entry.get('effective_status') or 'UNKNOWN'),
                          'spend': None, 'clicks': None, 'impressions': None,
                          'conversions': None, 'conversion_value': None,
                          'ctr_percent': None, 'cpa': None, 'roas': None})
        # Insights must be complete for reliable alerts; no silent partial success.
        try:
            fields='campaign_id,spend,clicks,impressions'
            params={'level':'campaign','fields':fields,'date_preset':'last_7d','limit':META_PAGE_SIZE}
            if chosen_action:
                # One exact conversion event; explicit click attribution window.
                params['fields']+=',actions,action_values,account_currency'
                params['action_attribution_windows']='["7d_click"]'
                params['action_report_time']='conversion'
            insight_rows=await _meta_pages(client,base+'/insights',headers,params)
            values={}
            for item in insight_rows:
                if not isinstance(item,dict):
                    raise ValueError('Invalid insight row')
                campaign_id=str(item.get('campaign_id',''))
                if not ID.fullmatch(campaign_id) or campaign_id in values:
                    raise ValueError('Invalid or duplicate insight')
                values[campaign_id]=item
            for c in found:
                row=values.get(c['id'])
                if not row:
                    continue
                spend=float(row['spend'])
                clicks=int(row['clicks'])
                impressions=int(row['impressions'])
                if not math.isfinite(spend) or spend<0 or clicks<0 or impressions<0:
                    continue
                c['spend']=round(spend,2)
                c['clicks']=clicks
                c['impressions']=impressions
                c['ctr_percent']=round(100*clicks/impressions,2) if impressions else None
                if chosen_action and row.get('account_currency')==acc['currency']:
                    count=_meta_action_number(row.get('actions'),chosen_action)
                    if count is None:
                        continue
                    c['conversions']=round(count,2)
                    c['conversion_action_type']=chosen_action
                    c['conversion_source']='meta_actions_7d_click'
                    c['cpa']=round(spend/count,2) if count>0 else None
                    from .goals import META_PURCHASE_ACTIONS
                    if chosen_action in META_PURCHASE_ACTIONS:
                        value=_meta_action_number(row.get('action_values'),chosen_action)
                        if value is not None:
                            c['conversion_value']=round(value,2)
                            c['roas']=round(value/spend,3) if spend>0 else None
        except HTTPException:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise HTTPException(502, 'Không thể đọc đầy đủ Meta Insights; không tạo cảnh báo dựa trên dữ liệu thiếu.') from None
        return found
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        raise HTTPException(502, 'Không đọc đủ chiến dịch Meta; kiểm tra phân trang và quyền API.') from None


async def list_live_campaigns(acc):
    if acc['platform'] not in ('google', 'meta') or not acc.get('token_ciphertext'):
        raise HTTPException(422, 'Chỉ hỗ trợ tài khoản Google/Meta đã kết nối API thật.')
    async with httpx.AsyncClient(timeout=httpx.Timeout(25, connect=7), trust_env=False) as client:
        return await (google_campaigns(acc,client) if acc['platform']=='google' else meta_campaigns(acc,client))


def rule_suggestions(campaigns, platform, currency):
    """Read-only heuristics, not optimization decisions or instructions to auto-pause."""
    result=[]
    for c in campaigns:
        if c['status'] not in ('ENABLED', 'ACTIVE') or c['clicks'] is None:
            continue
        if c['clicks']>=100 and c['impressions']>=1000 and (c['ctr_percent'] or 0)<0.5:
            result.append({'campaign_id':c['id'], 'level':'review', 'code':'low_ctr',
                           'message':'CTR dưới 0,5% với ít nhất 100 lượt nhấp: kiểm tra mục tiêu, nội dung và truy vấn; không tự tắt quảng cáo.'})
        if platform=='google' and c['clicks']>=100 and c['conversions']==0:
            result.append({'campaign_id':c['id'], 'level':'review', 'code':'no_reported_conversions',
                           'message':'Ít nhất 100 lượt nhấp nhưng chưa ghi nhận chuyển đổi: kiểm tra tracking và độ trễ chuyển đổi trước khi tối ưu CPA.'})
    return result[:40]


@app.get('/api/optimizations/accounts/{account_id}')
async def campaign_insights(account_id:int, ident=Depends(require('admin','operator','reader'))):
    acc=get_account(account_id,ident['org_id'])
    campaigns=await list_live_campaigns(acc)
    return {'account_id':acc['id'],'platform':acc['platform'],'currency':acc['currency'],
            'period':'last_7d','campaigns':campaigns,
            'recommendations':rule_suggestions(campaigns,acc['platform'],acc['currency']),
            'note': 'Chỉ đọc API. Meta CPA/ROAS chỉ tính cho một sự kiện được chọn, cửa sổ 7d_click, '
                    'đúng tiền tệ và có actions/action_values hợp lệ. Không đủ dữ liệu thì để trống; không tự chỉnh Ads.'}
