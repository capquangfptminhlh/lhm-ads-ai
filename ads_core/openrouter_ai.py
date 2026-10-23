"""Opt-in OpenRouter read-only advertising advisor. Never exposes account credentials.

Only aggregate performance, period and the user's message leave the machine.
The user explicitly enables this transfer in an admin-only setting.
"""
import asyncio
import json
import re
import time
from datetime import datetime, timezone
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
DEFAULT_DAILY_LIMIT = 30
# Cap calls per tenant per UTC date to protect against bill spikes. Not a monetary budget.

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
        fields={r['name'] for r in db.execute('PRAGMA table_info(openrouter_settings)')}
        if 'daily_limit' not in fields:
            db.execute('ALTER TABLE openrouter_settings ADD COLUMN daily_limit INTEGER NOT NULL DEFAULT 30')
        db.execute('''CREATE TABLE IF NOT EXISTS ai_daily_usage (
            org_id TEXT NOT NULL, day_utc TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(org_id,day_utc)
        )''')


def utc_day():
    return datetime.now(timezone.utc).date().isoformat()


def read_config(org_id):
    init_ai_settings()
    with connection() as db:
        row=db.execute('SELECT * FROM openrouter_settings WHERE org_id=?',(org_id,)).fetchone()
        usage=db.execute('SELECT request_count,prompt_tokens,completion_tokens FROM ai_daily_usage WHERE org_id=? AND day_utc=?',
                         (org_id,utc_day())).fetchone()
    return {'model': row['model'] if row else DEFAULT_MODEL,
            'enabled': bool(row['enabled']) if row else False,
            'configured': bool(row['token_ciphertext']) if row else False,
            'daily_limit': row['daily_limit'] if row else DEFAULT_DAILY_LIMIT,
            'used_today': usage['request_count'] if usage else 0,
            'tokens_today': ((usage['prompt_tokens']+usage['completion_tokens']) if usage else 0),
            'day_utc': utc_day(), 'privacy': 'zdr_required'}


def reserve_daily_call(org_id, limit):
    """Atomic per-tenant admission; counted even on upstream errors to avoid costly retry storms."""
    day=utc_day()
    with connection() as db:
        db.execute('INSERT OR IGNORE INTO ai_daily_usage(org_id,day_utc) VALUES(?,?)',(org_id,day))
        cur=db.execute('UPDATE ai_daily_usage SET request_count=request_count+1 WHERE org_id=? AND day_utc=? AND request_count<?',
                       (org_id,day,limit))
        if cur.rowcount!=1:
            raise HTTPException(429, f'Đã dùng hết {limit} lượt OpenRouter trong ngày (UTC). Thử lại ngày mai.')


def store_usage(org_id, usage):
    try:
        prompt=max(0,min(int(usage.get('prompt_tokens',0) or 0),10000000))
        completion=max(0,min(int(usage.get('completion_tokens',0) or 0),10000000))
    except (ValueError,TypeError,AttributeError):
        return
    with connection() as db:
        db.execute('UPDATE ai_daily_usage SET prompt_tokens=prompt_tokens+?,completion_tokens=completion_tokens+? WHERE org_id=? AND day_utc=?',
                   (prompt,completion,org_id,utc_day()))


class AISettingsInput(BaseModel):
    model: str = Field(default=DEFAULT_MODEL, min_length=4, max_length=140, pattern=MODEL_PATTERN)
    api_key: str = Field(default='', max_length=512)
    enabled: bool = False
    daily_limit: int = Field(default=DEFAULT_DAILY_LIMIT, ge=1, le=200)


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
        db.execute('''INSERT INTO openrouter_settings(org_id,token_ciphertext,model,enabled,daily_limit)
                      VALUES(?,?,?,?,?) ON CONFLICT(org_id) DO UPDATE SET
                      token_ciphertext=excluded.token_ciphertext,model=excluded.model,
                      enabled=excluded.enabled,daily_limit=excluded.daily_limit,updated_at=CURRENT_TIMESTAMP''',
                   (ident['org_id'], ciphertext, payload.model, int(payload.enabled), payload.daily_limit))
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
    """Best-effort masking. Do not claim that arbitrary names or secrets are detected."""
    patterns=(
      r'(?i)\b(?:sk-or-[A-Za-z0-9._-]{8,}|sk-[A-Za-z0-9_-]{16,}|bearer\s+\S+|EA[A-Za-z0-9]{30,})',
      r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',
      r'(?i)https?://\S+',
      r'(?<![\w])(?:\+?\d[\d .()-]{8,}\d)(?![\w])',
      r'\b\d{8,30}\b',
    )
    for pattern in patterns:
        text=re.sub(pattern,'[đã ẩn thông tin nhạy cảm]',text)
    return text[:1200]


def sanitized_rollup(data):
    """Whitelisted numeric fields only. No campaign IDs, account labels or API errors.

    Conversion totals are included only when EVERY account in the group
    actually supplied them (the same rule report_output uses): a provider
    that did not report conversions must not silently count as zero, and
    CPA/ROAS are derived only from complete totals.
    """
    groups = {}
    complete = {}
    for item in data['accounts']:
        r = item.get('result')
        if not r:
            continue
        # Keep demo separated and clearly identified.
        key = (item['platform'] if item['platform'] in ('demo','meta','google','tiktok','openai') else 'other',
               r.get('currency','?'), r.get('source') == 'demo')
        g = groups.setdefault(key, {'platform': key[0], 'currency': key[1], 'demo': key[2],
                                    'accounts': 0, 'spend': 0.0, 'impressions': 0, 'clicks': 0,
                                    'conversions': 0.0, 'conversion_value': 0.0})
        c = complete.setdefault(key, {'conversions': True, 'conversion_value': True})
        g['accounts'] += 1
        g['spend'] += float(r.get('spend') or 0)
        g['impressions'] += int(r.get('impressions') or 0)
        g['clicks'] += int(r.get('clicks') or 0)
        for field in ('conversions', 'conversion_value'):
            if r.get(field) is None:
                c[field] = False
            else:
                g[field] += float(r[field])
    any_conversions = False
    for key, g in groups.items():
        g['spend'] = round(g['spend'], 2)
        g['ctr_percent'] = round(100*g['clicks']/g['impressions'], 2) if g['impressions'] else 0
        c = complete[key]
        if c['conversions']:
            any_conversions = True
            g['conversions'] = round(g['conversions'], 2)
            g['cpa'] = round(g['spend']/g['conversions'], 2) if g['conversions'] > 0 else None
        else:
            g['conversions'] = None
            g['cpa'] = None
        if c['conversions'] and c['conversion_value']:
            g['conversion_value'] = round(g['conversion_value'], 2)
            g['roas'] = round(g['conversion_value']/g['spend'], 2) if g['spend'] > 0 else None
        else:
            g['conversion_value'] = None
            g['roas'] = None
    note = ('Số liệu demo không phải hiệu suất thật. CPA/ROAS chỉ có ở nhóm mà mọi '
            'tài khoản đều báo cáo chuyển đổi/doanh thu; nhóm để trống là dữ liệu chưa đầy đủ, không phải 0.')
    if not any_conversions:
        note = 'Không có dữ liệu chuyển đổi/doanh thu: không thể xác định CPA, ROAS. ' + note
    return {'period':data['period'], 'groups':list(groups.values()),
            'unavailable_account_count':sum('error' in x for x in data['accounts']),
            'note':note}


SYSTEM = ('Bạn là chuyên gia phân tích hiệu suất quảng cáo bằng tiếng Việt. '
          'Chỉ phân tích số liệu tổng hợp được cung cấp, tách biệt loại tiền tệ và dữ liệu demo. '
          'Không tự tạo số liệu, ROAS, CPA hoặc chuyển đổi nếu thiếu dữ liệu. '
          'Đưa khuyến nghị cụ thể, nêu giới hạn của số liệu. '
          'Bạn KHÔNG có quyền điều khiển chiến dịch, không gọi công cụ, không cấp lệnh đổi ngân sách. '
          'Nếu được yêu cầu tắt/sửa chiến dịch, chỉ hướng dẫn người dùng tạo yêu cầu và chờ quản trị viên duyệt. '
          'Không được giả nhận đã triển khai thay đổi nào.')


async def openrouter_answer(ident, message, period, date_from=None, date_to=None):
    init_ai_settings()
    org = ident['org_id']
    with connection() as db:
        cfg = db.execute('SELECT * FROM openrouter_settings WHERE org_id=?', (org,)).fetchone()
    if not cfg or not cfg['enabled'] or not cfg['token_ciphertext']:
        return None
    if __import__('os').environ.get('LHM_DESKTOP_MODE') == '1':
        from .licensing import license_required
        license_required()
    if ident['role'] == 'reader':
        raise HTTPException(403, 'Chỉ Admin/Operator được gọi AI có tính phí')
    now = time.monotonic()
    ident_key = (org, ident['id'])
    CALLS[ident_key] = [t for t in CALLS[ident_key] if now-t < 300]
    if len(CALLS[ident_key]) >= 10:
        raise HTTPException(429, 'Giới hạn 10 yêu cầu AI trong 5 phút')
    CALLS[ident_key].append(now)
    key = unseal(cfg['token_ciphertext'],f'openrouter:{org}')
    data = await summary(period=period,date_from=date_from,date_to=date_to,ident=ident)
    rollup = sanitized_rollup(data)
    reserve_daily_call(org, cfg['daily_limit'])
    payload = {
      'model': cfg['model'],
      'provider': {'zdr': True, 'data_collection': 'deny'},
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
        if resp.status_code == 400:
            raise HTTPException(422, 'Model không hỗ trợ tuyến Zero Data Retention hoặc tham số không hợp lệ. Hãy chọn model có nhà cung cấp ZDR.')
        if resp.status_code == 429:
            raise HTTPException(429, 'OpenRouter đang giới hạn yêu cầu; thử lại sau.')
        if resp.status_code >= 400:
            raise HTTPException(502, f'OpenRouter không xử lý được yêu cầu (HTTP {resp.status_code}).')
        body = resp.json()
        response = body['choices'][0]['message']['content']
        if not isinstance(response, str) or not response.strip():
            raise ValueError('Empty model response')
        store_usage(org, body.get('usage') or {})
        return {'reply': response[:12000], 'mode':'openrouter', 'model':cfg['model'],
                'usage': {k:int(body.get('usage',{}).get(k,0) or 0)
                          for k in ('prompt_tokens','completion_tokens','total_tokens')},
                'disclaimer':'Đã gửi câu hỏi (lọc định dạng nhạy cảm) và thống kê tổng hợp tới OpenRouter qua ZDR. Có thể còn thông tin cá nhân người dùng tự gõ; đừng nhập bí mật. AI chỉ tư vấn.'}
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        # Don't expose provider response, credentials or raw request details to logs/browser.
        raise HTTPException(502, 'Không thể nhận phân tích từ OpenRouter. Kiểm tra mạng, model và tài khoản.') from None


@app.post('/api/ai/diagnostics')
async def openrouter_diagnostics(ident=Depends(browser_admin)):
    """Explicit admin-triggered, non-billable connection test.

    Verify the stored OpenRouter key and availability of an exact ZDR model.
    Never submit a prompt, use chat completions, modify the license, consume
    local daily AI quota, or return any credential/provider error payload.
    """
    org = ident['org_id']
    cfg = read_config(org)
    desktop = __import__('os').environ.get('LHM_DESKTOP_MODE') == '1'
    license_state = {'active': True, 'reason': 'not_required'}
    if desktop:
        from .licensing import read_license
        try:
            current = read_license()
            license_state = {'active': bool(current.get('active')),
                             'reason': 'active' if current.get('active')
                                       else str(current.get('reason', 'not_active'))}
        except (OSError, ValueError, KeyError, TypeError):
            license_state = {'active': False, 'reason': 'check_failed'}
    result = {
        'mode': 'non_billable_diagnostics',
        'enabled': cfg['enabled'],
        'configured': cfg['configured'],
        'model': cfg['model'],
        'daily_limit': cfg['daily_limit'],
        'used_today': cfg['used_today'],
        'license': license_state,
        'key_status': 'not_configured',
        'model_status': 'not_checked',
        'ready_for_ai': False,
        'chat_tested': False,
    }
    if not cfg['configured']:
        return result
    with connection() as db:
        row = db.execute('SELECT token_ciphertext FROM openrouter_settings WHERE org_id=?',
                         (org,)).fetchone()
    if not row or not row['token_ciphertext']:
        return result
    try:
        key = unseal(row['token_ciphertext'], f'openrouter:{org}')
    except (ValueError, TypeError, KeyError):
        result['key_status'] = 'local_decryption_failed'
        return result
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=5),
                                     trust_env=False, follow_redirects=False) as client:
            key_response = await client.get('https://openrouter.ai/api/v1/key',
                                            headers={'Authorization': 'Bearer ' + key})
            if key_response.status_code == 401:
                result['key_status'] = 'invalid'
                return result
            if key_response.status_code == 403:
                result['key_status'] = 'rejected'
                return result
            if key_response.status_code == 429:
                result['key_status'] = 'rate_limited'
                return result
            if key_response.status_code != 200:
                result['key_status'] = 'provider_unavailable'
                return result
            info = key_response.json()
            if not isinstance(info, dict) or not isinstance(info.get('data'), dict):
                result['key_status'] = 'invalid_response'
                return result
            result['key_status'] = 'valid'
            remaining = info['data'].get('limit_remaining')
            if isinstance(remaining, (float, int)) and not isinstance(remaining, bool):
                result['key_limit_exhausted'] = remaining <= 0
            else:
                result['key_limit_exhausted'] = False
            # OpenRouter models API supports q and zdr=true. Compare exact
            # model IDs; substring/search matches must never count as ready.
            model_response = await client.get('https://openrouter.ai/api/v1/models',
                                              headers={'Authorization': 'Bearer ' + key},
                                              params={'q': cfg['model']})
            if model_response.status_code != 200:
                result['model_status'] = 'provider_unavailable'
                return result
            models = model_response.json()
            if not isinstance(models, dict) or not isinstance(models.get('data'), list):
                result['model_status'] = 'invalid_response'
                return result
            if not any(isinstance(m, dict) and m.get('id') == cfg['model']
                       for m in models['data']):
                result['model_status'] = 'not_found'
                return result
            zdr_response = await client.get('https://openrouter.ai/api/v1/models',
                                            headers={'Authorization': 'Bearer ' + key},
                                            params={'q': cfg['model'], 'zdr': 'true'})
            if zdr_response.status_code != 200:
                result['model_status'] = 'provider_unavailable'
                return result
            zdr = zdr_response.json()
            if not isinstance(zdr, dict) or not isinstance(zdr.get('data'), list):
                result['model_status'] = 'invalid_response'
                return result
            result['model_status'] = (
                'zdr_available'
                if any(isinstance(m, dict) and m.get('id') == cfg['model']
                       for m in zdr['data'])
                else 'zdr_unavailable'
            )
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        if result['key_status'] != 'valid':
            result['key_status'] = 'network_error'
        elif result['model_status'] == 'not_checked':
            result['model_status'] = 'network_error'
        return result
    result['ready_for_ai'] = bool(
        result['enabled'] and result['key_status'] == 'valid'
        and result['model_status'] == 'zdr_available'
        and not result.get('key_limit_exhausted', False)
        and license_state['active']
        and result['used_today'] < result['daily_limit']
    )
    return result


class PreviewRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1200)
    period: str = Field(default='last_7d', pattern=r'^(today|yesterday|last_(7|14|30|90)d|this_(week|month|quarter|year)|last_(week|month|quarter|year)|custom)$')
    date_from: str | None = None
    date_to: str | None = None


@app.post('/api/ai/preview')
async def privacy_preview(payload: PreviewRequest, ident=Depends(require('admin','operator','reader'))):
    """Local-only preview of outgoing content. NEVER calls OpenRouter or uses AI quota."""
    data=await summary(period=payload.period,date_from=payload.date_from,date_to=payload.date_to,ident=ident)
    return {'question':scrub_user_message(payload.message),
            'statistics':sanitized_rollup(data),
            'routing':{'zdr':True,'data_collection':'deny'},
            'notice':'Bản xem trước trên máy; văn bản có thể chứa tên riêng không được tự động nhận diện.'}
