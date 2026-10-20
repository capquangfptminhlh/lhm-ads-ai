"""Opt-in OpenRouter read-only advertising advisor. Never exposes account credentials.

Only aggregate performance, period and the user's message leave the machine.
The user explicitly enables this transfer in an admin-only setting.
"""
import asyncio
import json
import re
import time
from collections import defaultdict

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .app import app, browser_admin, require, summary
from .db import audit, connection
from .security import seal, unseal

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
MODEL_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9._:-]*/[A-Za-z0-9][A-Za-z0-9._:-]*$'
DEFAULT_MODEL = 'openai/gpt-4.1-mini'
# Per-process limits: intended for desktop/one-worker VPS deployment.
CALLS = defaultdict(list)
SEM = asyncio.Semaphore(3)


def init_ai_settings():
    with connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS openrouter_settings (
            org_id TEXT PRIMARY KEY, token_ciphertext TEXT,
            model TEXT NOT NULL DEFAULT 'openai/gpt-4.1-mini',
            enabled INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')


def read_config(org_id):
    init_ai_settings()
    with connection() as db:
        row = db.execute('SELECT * FROM openrouter_settings WHERE org_id=?', (org_id,)).fetchone()
    if not row:
        return {'model': DEFAULT_MODEL, 'enabled': False, 'configured': False}
    return {'model': row['model'], 'enabled': bool(row['enabled']), 'configured': bool(row['token_ciphertext'])}


class AISettingsInput(BaseModel):
    model: str = Field(default=DEFAULT_MODEL, min_length=4, max_length=140, pattern=MODEL_PATTERN)
    api_key: str = Field(default='', max_length=512)
    enabled: bool = False


@app.get('/api/ai/settings')
def ai_settings(ident=Depends(require('admin','operator','reader'))):
    return read_config(ident['org_id'])


@app.put('/api/ai/settings')
def update_ai_settings(payload: AISettingsInput, ident=Depends(browser_admin)):
    init_ai_settings()
    key = payload.api_key.strip()
    if key and (len(key) < 16 or not key.startswith('sk-or-')):
        raise HTTPException(422, 'OpenRouter API key không hợp lệ')
    with connection() as db:
        old = db.execute('SELECT token_ciphertext FROM openrouter_settings WHERE org_id=?', (ident['org_id'],)).fetchone()
        ciphertext = seal(key, f'openrouter:{ident["org_id"]}') if key else old['token_ciphertext'] if old else None
        if payload.enabled and not ciphertext:
            raise HTTPException(422, 'Hãy thêm API key trước khi bật OpenRouter')
        db.execute('''INSERT INTO openrouter_settings(org_id,token_ciphertext,model,enabled)
                      VALUES(?,?,?,?) ON CONFLICT(org_id) DO UPDATE SET
                      token_ciphertext=excluded.token_ciphertext,model=excluded.model,
                      enabled=excluded.enabled,updated_at=CURRENT_TIMESTAMP''',
                   (ident['org_id'], ciphertext, payload.model, int(payload.enabled)))
        audit(db, ident, 'ai.settings', f'OpenRouter enabled={payload.enabled}; model={payload.model}')
    return read_config(ident['org_id'])


@app.delete('/api/ai/settings')
def disable_ai_settings(ident=Depends(browser_admin)):
    init_ai_settings()
    with connection() as db:
        db.execute('DELETE FROM openrouter_settings WHERE org_id=?', (ident['org_id'],))
        audit(db, ident, 'ai.revoked', 'OpenRouter API key deleted')
    return {'ok': True}


def scrub_user_message(text):
    # Never relay accidentally pasted provider or OpenRouter keys.
    return re.sub(r'(?i)(?:sk-or-[A-Za-z0-9._-]{8,}|sk-[A-Za-z0-9_-]{16,}|bearer\s+\S+|EA[A-Za-z0-9]{30,})',
                  '[đã ẩn thông tin bí mật]', text)[:1200]


def sanitized_rollup(data):
    """Whitelisted numeric fields only. No campaign IDs, account labels or API errors."""
    groups = {}
    for item in data['accounts']:
        r = item.get('result')
        if not r:
            continue
        # Keep demo separated and clearly identified.
        key = (item['platform'] if item['platform'] in ('demo','meta','google','tiktok','openai') else 'other',
               r.get('currency','?'), r.get('source') == 'demo')
        g = groups.setdefault(key, {'platform': key[0], 'currency': key[1], 'demo': key[2],
                                    'accounts': 0, 'spend': 0.0, 'impressions': 0, 'clicks': 0})
        g['accounts'] += 1
        g['spend'] += float(r.get('spend') or 0)
        g['impressions'] += int(r.get('impressions') or 0)
        g['clicks'] += int(r.get('clicks') or 0)
    for g in groups.values():
        g['spend'] = round(g['spend'], 2)
        g['ctr_percent'] = round(100*g['clicks']/g['impressions'], 2) if g['impressions'] else 0
    return {'period':data['period'], 'groups':list(groups.values()),
            'unavailable_account_count':sum('error' in x for x in data['accounts']),
            'note':'Không có dữ liệu chuyển đổi/doanh thu: không thể xác định CPA, ROAS; số liệu demo không phải hiệu suất thật.'}


SYSTEM = ('Bạn là chuyên gia phân tích hiệu suất quảng cáo bằng tiếng Việt. '
          'Chỉ phân tích số liệu tổng hợp được cung cấp, tách biệt loại tiền tệ và dữ liệu demo. '
          'Không tự tạo số liệu, ROAS, CPA hoặc chuyển đổi nếu thiếu dữ liệu. '
          'Đưa khuyến nghị cụ thể, nêu giới hạn của số liệu. '
          'Bạn KHÔNG có quyền điều khiển chiến dịch, không gọi công cụ, không cấp lệnh đổi ngân sách. '
          'Nếu được yêu cầu tắt/sửa chiến dịch, chỉ hướng dẫn người dùng tạo yêu cầu và chờ quản trị viên duyệt. '
          'Không được giả nhận đã triển khai thay đổi nào.')


async def openrouter_answer(ident, message, period):
    init_ai_settings()
    org = ident['org_id']
    with connection() as db:
        cfg = db.execute('SELECT * FROM openrouter_settings WHERE org_id=?', (org,)).fetchone()
    if not cfg or not cfg['enabled'] or not cfg['token_ciphertext']:
        return None
    if ident['role'] == 'reader':
        raise HTTPException(403, 'Chỉ Admin/Operator được gọi AI có tính phí')
    now = time.monotonic()
    ident_key = (org, ident['id'])
    CALLS[ident_key] = [t for t in CALLS[ident_key] if now-t < 300]
    if len(CALLS[ident_key]) >= 10:
        raise HTTPException(429, 'Giới hạn 10 yêu cầu AI trong 5 phút')
    CALLS[ident_key].append(now)
    key = unseal(cfg['token_ciphertext'],f'openrouter:{org}')
    data = await summary(period=period, ident=ident)
    rollup = sanitized_rollup(data)
    payload = {
      'model': cfg['model'],
      'messages': [{'role':'system','content':SYSTEM},
                   {'role':'user','content':json.dumps({'question':scrub_user_message(message),
                                  'statistics':rollup},ensure_ascii=False)}],
      'temperature': 0.2,
      'max_tokens': 900,
      'stream': False,
    }
    try:
        async with SEM:
            async with httpx.AsyncClient(timeout=httpx.Timeout(35.0,connect=8.0),trust_env=False) as client:
                resp = await client.post(OPENROUTER_URL, headers={
                    'Authorization': 'Bearer ' + key,
                    'Content-Type': 'application/json',
                    'X-Title': 'LHM Ads AI'}, json=payload)
        if resp.status_code == 401:
            raise HTTPException(502, 'API key OpenRouter không được chấp nhận. Kiểm tra lại trong Cài đặt.')
        if resp.status_code == 429:
            raise HTTPException(429, 'OpenRouter đang giới hạn yêu cầu; thử lại sau.')
        if resp.status_code >= 400:
            raise HTTPException(502, f'OpenRouter không xử lý được yêu cầu (HTTP {resp.status_code}).')
        body = resp.json()
        response = body['choices'][0]['message']['content']
        if not isinstance(response, str) or not response.strip():
            raise ValueError('Empty model response')
        return {'reply': response[:12000], 'mode':'openrouter', 'model':cfg['model'],
                'usage': {k:int(body.get('usage',{}).get(k,0) or 0)
                          for k in ('prompt_tokens','completion_tokens','total_tokens')},
                'disclaimer':'Đã gửi câu hỏi và thống kê tổng hợp (KHÔNG gồm tên/ID tài khoản, token) sang OpenRouter. AI chỉ tư vấn, không tự chỉnh quảng cáo.'}
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        # Don't expose provider response, credentials or raw request details to logs/browser.
        raise HTTPException(502, 'Không thể nhận phân tích từ OpenRouter. Kiểm tra mạng, model và tài khoản.') from None
