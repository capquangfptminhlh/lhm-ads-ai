"""Explicit admin-approved Google PAUSE only. No budget/bid/strategy writes.

Always reads the actual campaign under the target account before mutating;
validates the exact operation, and never auto-executes an LLM suggestion.
"""
import re
import httpx
from fastapi import HTTPException
from .optimizations import google_access

async def pause_google_campaign(acc, campaign_id):
    if acc['platform']!='google' or not re.fullmatch(r'\d{5,30}', campaign_id):
        raise HTTPException(422,'Chỉ hỗ trợ tạm dừng Google Campaign hợp lệ.')
    async with httpx.AsyncClient(timeout=httpx.Timeout(30,connect=8),trust_env=False) as client:
        customer, version, headers = await google_access(client,acc)
        path=f'https://googleads.googleapis.com/{version}/customers/{customer}'
        query=(f'SELECT campaign.id,campaign.status FROM campaign '
               f'WHERE campaign.id = {campaign_id} LIMIT 1')
        try:
            observed=await client.post(path+'/googleAds:searchStream',headers=headers,json={'query':query})
            observed.raise_for_status()
            entries=[v['campaign'] for page in observed.json() for v in page.get('results',[]) if isinstance(v.get('campaign'),dict)]
            if len(entries)!=1 or str(entries[0].get('id'))!=campaign_id:
                raise HTTPException(404,'Chiến dịch không thuộc tài khoản Google Ads đã chọn.')
            status=entries[0].get('status')
            if status!='ENABLED':
                raise HTTPException(409,f'Chỉ tạm dừng khi chiến dịch đang ENABLED, hiện tại {status}.')
            operation={'update':{'resourceName':f'customers/{customer}/campaigns/{campaign_id}',
                                 'status':'PAUSED'},'updateMask':'status'}
            # Google Ads validateOnly detects permission/policy errors without a real mutation.
            dry=await client.post(path+'/campaigns:mutate',headers=headers,
                                  json={'operations':[operation],'validateOnly':True,'partialFailure':False})
            if dry.status_code!=200:
                raise HTTPException(403,'Google Ads từ chối kiểm tra quyền chỉnh sửa (validateOnly).')
            live=await client.post(path+'/campaigns:mutate',headers=headers,
                                   json={'operations':[operation],'validateOnly':False,'partialFailure':False})
            live.raise_for_status()
            body=live.json()
            if not body.get('results') or body['results'][0].get('resourceName')!=operation['update']['resourceName']:
                raise ValueError('Google Ads mutation not confirmed by response')
            # API accepted update; actual propagation may be delayed. Never claim read-after-write verified.
            return {'success':True,'provider_accepted':True,'verification':'API xác nhận tiếp nhận lệnh; chưa kiểm tra trạng thái sau đồng bộ.'}
        except httpx.HTTPError:
            raise HTTPException(502,'Lỗi Google Ads khi kiểm tra hoặc cập nhật chiến dịch; không tự gửi lại lệnh.') from None
        except (ValueError,TypeError,KeyError,IndexError):
            raise HTTPException(502,'Google Ads trả về dữ liệu không hợp lệ; kiểm tra chiến dịch trước khi thử lại.') from None
