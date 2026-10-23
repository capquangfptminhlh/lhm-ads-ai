"""LHM Ads AI Studio: private on-server report analysis and staff management.

Uses existing tenant-scoped services; never exposes provider tokens to a model.
"""
import re
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from .app import app, browser_admin, identify, require, summary
from .db import audit, connection
from .security import hash_password, make_secret

STATIC = Path(__file__).resolve().parent.parent / 'static'
# Preserve old dashboard as /classic while making the redesigned studio the home.
app.router.routes[:] = [r for r in app.router.routes if not (isinstance(r, APIRoute) and r.path == '/')]

@app.get('/', include_in_schema=False)
def entry():
    return RedirectResponse('/studio', status_code=307)

@app.get('/studio', include_in_schema=False)
def studio():
    return FileResponse(STATIC / 'studio.html')

# Installable PWA routes are deliberately public static resources; API and
# authenticated Studio pages are never cached by the service worker.
@app.get('/manifest.webmanifest', include_in_schema=False)
def pwa_manifest():
    return FileResponse(STATIC / 'manifest.webmanifest', media_type='application/manifest+json')

@app.get('/sw.js', include_in_schema=False)
def pwa_service_worker():
    return FileResponse(STATIC / 'sw.js', media_type='text/javascript',
                        headers={'Service-Worker-Allowed': '/'})

class ChatInput(BaseModel):
    message: str = Field(min_length=2, max_length=1200)
    period: str = Field(default='last_7d', pattern=r'^(today|yesterday|last_(7|14|30|90)d|this_(week|month|quarter|year)|last_(week|month|quarter|year)|custom)$')
    date_from: str | None = None
    date_to: str | None = None


def num(value):
    return f'{value:,.0f}'.replace(',', '.')


def grounded_answer(message, data):
    items = [x for x in data['accounts'] if 'result' in x]
    failed = [x for x in data['accounts'] if 'error' in x]
    if not items:
        return ('Chưa có số liệu có thể đọc. Hãy thêm tài khoản Demo để trải nghiệm, '
                'hoặc kết nối Meta/Google bằng API chính thức. Không có dữ liệu giả cho tài khoản thật.')
    currencies = {}
    for item in items:
        r = item['result']
        currencies.setdefault(r['currency'], []).append(item)
    parts = [f'Báo cáo {"hôm qua" if data["period"] == "yesterday" else "7 ngày gần nhất"} '
             f'từ {len(items)} tài khoản; {len(failed)} tài khoản chưa lấy được dữ liệu.']
    for currency, group in currencies.items():
        spend = sum(x['result']['spend'] for x in group)
        clicks = sum(x['result']['clicks'] for x in group)
        impressions = sum(x['result']['impressions'] for x in group)
        parts.append(f'{currency}: chi {num(spend)}, {num(clicks)} click, '
                     f'{num(impressions)} lần hiển thị; CTR {100 * clicks / impressions:.2f}%' if impressions else
                     f'{currency}: chi {num(spend)}, không có lượt hiển thị để tính CTR.')
        top = max(group, key=lambda x: x['result']['spend'])
        parts.append(f'Tài khoản chi nhiều nhất bằng {currency}: {top["label"]} ({num(top["result"]["spend"])}).')
    if any(x['result']['source'] == 'demo' for x in items):
        parts.append('Có DỮ LIỆU DEMO minh họa, không phải số liệu quảng cáo thật.')
    if failed:
        parts.append('Một số nguồn chưa hoạt động: ' + '; '.join(f'{x["label"]}: {str(x["error"])[:90]}' for x in failed[:3]))
    parts.append('Chưa có dữ liệu chuyển đổi/doanh thu nên không thể xác định CPA hay ROAS; không tự bật/tắt quảng cáo.')
    return '\n'.join(parts)

from .openrouter_ai import openrouter_answer

@app.post('/api/assistant/chat')
async def assistant_chat(payload: ChatInput, ident=Depends(require('admin', 'operator', 'reader'))):
    ai_reply = await openrouter_answer(ident, payload.message, payload.period,
                                      date_from=payload.date_from,date_to=payload.date_to)
    if ai_reply is not None:
        return ai_reply
    data = await summary(period=payload.period,date_from=payload.date_from,
                         date_to=payload.date_to,ident=ident)
    explanation = grounded_answer(payload.message, data)
    # Privacy-first: only deterministic local analysis. Never export report data to LLM services.
    return {'reply': explanation, 'mode': 'analyst', 'sources': data['totals']['sources'],
            'disclaimer': 'Phân tích trên VPS; không gửi dữ liệu cho AI bên ngoài.'}

class TeamInput(BaseModel):
    email: str = Field(min_length=5,max_length=254)
    role: str = Field(pattern=r'^(reader|operator|admin)$')

@app.get('/api/studio/me')
def studio_me(ident=Depends(identify)):
    return {'id':ident['id'],'email':ident['email'],'role':ident['role'],
            'org_id':ident['org_id'],'csrf':ident.get('csrf') if ident['auth_type']=='browser' else None}

@app.get('/api/team')
def team(ident=Depends(browser_admin)):
    with connection() as db:
        return [dict(row) for row in db.execute('SELECT id,email,role,disabled,created_at FROM users WHERE org_id=? ORDER BY id',(ident['org_id'],))]

@app.post('/api/team')
def add_user(payload: TeamInput, ident=Depends(browser_admin)):
    email = payload.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise HTTPException(422,'Email không hợp lệ')
    pwd = make_secret()[:28] + 'Z9!'
    with connection() as db:
        try:
            cur=db.execute('INSERT INTO users (org_id,email,role,password_hash) VALUES (?,?,?,?)',
                           (ident['org_id'],email,payload.role,hash_password(pwd)))
        except __import__('sqlite3').IntegrityError:
            raise HTTPException(409,'Email đã được sử dụng')
        audit(db,ident,'team.create',f'Created user #{cur.lastrowid} as {payload.role}')
    return {'id':cur.lastrowid,'temporary_password':pwd,'warning':'Mật khẩu chỉ hiện một lần; chuyển qua kênh riêng an toàn.'}

@app.post('/api/team/{user_id}/disable')
def disable_user(user_id:int, ident=Depends(browser_admin)):
    if user_id==ident['id']:
        raise HTTPException(409,'Không thể vô hiệu hóa chính tài khoản đang dùng')
    with connection() as db:
        cur = db.execute('UPDATE users SET disabled=1 WHERE id=? AND org_id=? AND disabled=0',(user_id,ident['org_id']))
        if cur.rowcount!=1:
            raise HTTPException(404,'Không tìm thấy người dùng đang hoạt động')
        db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
        audit(db,ident,'team.disable',f'Disabled user #{user_id} and revoked sessions')
    return {'ok':True}

class PasswordInput(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12,max_length=256)

@app.post('/api/me/password')
def change_password(body: PasswordInput, ident=Depends(require('admin','operator','reader'))):
    from .security import (
        PASSWORD_CHANGE_MAX_ATTEMPTS, attempt_blocked, attempt_failed,
        attempt_succeeded, password_change_scope, verify_password,
    )
    scope = password_change_scope(ident['id'])
    with connection() as db:
        if attempt_blocked(db, scope, PASSWORD_CHANGE_MAX_ATTEMPTS):
            raise HTTPException(429,'Đã thử đổi mật khẩu quá nhiều lần. Vui lòng đợi 15 phút rồi thử lại.')
        u = db.execute('SELECT password_hash FROM users WHERE id=?',(ident['id'],)).fetchone()
        if not u or not verify_password(u['password_hash'],body.old_password):
            attempt_failed(db, scope)
            raise HTTPException(403,'Mật khẩu hiện tại không đúng')
        attempt_succeeded(db, scope)
        db.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(body.new_password),ident['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(ident['id'],))
        audit(db,ident,'auth.password_changed','Revoked all sessions on password change')
    return {'ok':True,'message':'Đổi mật khẩu thành công. Vui lòng đăng nhập lại.'}

@app.get('/api/export/reports')
async def export_report(period:str='last_7d',date_from:str|None=None,date_to:str|None=None,
                        ident=Depends(require('admin','operator','reader'))):
    import csv, io
    data=await summary(period=period,date_from=date_from,date_to=date_to,ident=ident)
    output=io.StringIO()
    writer=csv.writer(output)
    def safe(value):
        # Neutralize spreadsheet formula injection from account labels / API errors.
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
    writer.writerow(['account_id','label','platform','source','currency','date','spend','impressions','clicks','error'])
    for item in data['accounts']:
        if 'result' not in item:
            writer.writerow([safe(item['account_id']),safe(item['label']),safe(item['platform']),'','','','','','',safe(item['error'])])
        else:
            r=item['result']
            for day in r['daily']:
                writer.writerow([safe(item['account_id']),safe(item['label']),safe(item['platform']),safe(r['source']),safe(r['currency']),
                                 safe(day['date']),day['spend'],day['impressions'],day['clicks'],''])
    return Response(content='\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="lhm-ads-{period}.csv"'})

# Register server-side first-party OAuth routes (does not expose an MCP interface).
from . import oauth_connect  # noqa: E402,F401
from . import desktop_setup  # noqa: E402,F401

# Session-protected Internet status, used by Windows desktop auto-reconnect UI.
from . import network_status  # noqa: E402,F401

# Register local first-run UI. Guarded by desktop mode and loopback-only requests.
from . import desktop_onboarding  # noqa: E402,F401

# Commercial Windows: locally signed licenses and read-only monitoring.
from . import licensing, monitoring  # noqa: E402,F401

# Explicit, read-only OAuth/API permission diagnostics; no MCP access.
from . import permissions  # noqa: E402,F401

# Read-only campaign diagnostics; no automatic provider modifications.
from . import optimizations  # noqa: E402,F401

# Account-scoped Ads change plan endpoints; no unattended mutations.
from . import autopilot  # noqa: E402,F401

# Per-account CPA / ROAS goals, review-only; no provider write permission.
from . import goals  # noqa: E402,F401

# Read-only post-mutation verification; never retries provider writes.
from . import reconciliation  # noqa: E402,F401

# Local admin-only encrypted backup and commercial readiness checks.
from . import secure_backup, desktop_readiness  # noqa: E402,F401

# Optional per-user TOTP MFA enrolment/management endpoints.
from . import mfa  # noqa: E402,F401

# Explicit admin-provisioned, read-only MCP stdio access; no public MCP route.
from . import mcp_bridge  # noqa: E402,F401

# Opt-in daily budget thresholds and encrypted Web Push subscription endpoints.
from . import budget_push  # noqa: E402,F401
