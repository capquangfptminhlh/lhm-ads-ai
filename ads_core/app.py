"""LHM Ads AI: login, tenant-bound accounts, reporting and human-approved changes."""
import os
import re
import time
import json
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .version import __version__
from .db import connection, init_db, audit
from .security import (hash_secret, make_secret, verify_password, seal, validate_secrets)
from .providers import fetch_report, pause_meta_campaign
from .report_dates import resolve_date_range

@asynccontextmanager
async def lifespan(application):
    validate_secrets()
    init_db()
    yield

app = FastAPI(title='LHM Ads AI Starter', version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount('/static', StaticFiles(directory=str(Path(__file__).resolve().parent.parent/'static')), name='static')

@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'none'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    # Added 2026-10-21 (commercial security pass) — each fits this app:
    # - Permissions-Policy: the UI never uses camera/microphone/geolocation/
    #   payment/USB, so deny them outright for every document.
    # - Cross-Origin-Resource-Policy: API/static resources are only ever
    #   loaded by the app's own origin; provider OAuth is redirect-based
    #   (oauth_connect.py), never cross-origin embedding, so same-origin
    #   cannot break it.
    # - HSTS only when COOKIE_SECURE=true (HTTPS server mode): browsers
    #   ignore it over plain HTTP, and desktop loopback mode is HTTP-only,
    #   so emitting it there would promise a guarantee that does not exist.
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    if os.environ.get('COOKIE_SECURE', 'true').lower() == 'true':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response

@app.get('/')
async def home():
    return FileResponse(str(Path(__file__).resolve().parent.parent/'static'/'index.html'))

@app.get('/healthz')
async def health():
    return {'ok':True, 'version':__version__}

# Durable login throttling in the shared SQLite database: unlike the previous
# in-memory counters it survives restarts and is shared by every process using
# this database. Limits: 5 failures per email and 20 per source IP per 15
# minutes. A reverse proxy/WAF or Redis limiter is still recommended in front
# of multi-host deployments.
LOGIN_WINDOW_SECONDS = 900
LOGIN_MAX_PER_EMAIL = 5
LOGIN_MAX_PER_IP = 20

def _login_guard_init(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS login_attempts (
        scope TEXT NOT NULL,
        attempted_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_login_attempts_scope
        ON login_attempts(scope, attempted_at);
    ''')

def _login_blocked(db, email, ip, now):
    _login_guard_init(db)
    since = int(now) - LOGIN_WINDOW_SECONDS
    per_email = db.execute('SELECT COUNT(*) c FROM login_attempts WHERE scope=? AND attempted_at>?',
                           (f'email:{email}', since)).fetchone()['c']
    per_ip = db.execute('SELECT COUNT(*) c FROM login_attempts WHERE scope=? AND attempted_at>?',
                        (f'ip:{ip}', since)).fetchone()['c']
    return per_email >= LOGIN_MAX_PER_EMAIL or per_ip >= LOGIN_MAX_PER_IP

def _login_failed(db, email, ip, now):
    _login_guard_init(db)
    db.execute('INSERT INTO login_attempts(scope, attempted_at) VALUES(?,?)',
               (f'email:{email}', int(now)))
    db.execute('INSERT INTO login_attempts(scope, attempted_at) VALUES(?,?)',
               (f'ip:{ip}', int(now)))
    # Opportunistic prune so the table cannot grow without bound.
    db.execute('DELETE FROM login_attempts WHERE attempted_at<?', (int(now) - 86400,))
    # Commit immediately: the caller raises HTTPException for the failed
    # login, which would otherwise roll these counters back.
    db.commit()

def _login_succeeded(db, email):
    _login_guard_init(db)
    db.execute('DELETE FROM login_attempts WHERE scope=?', (f'email:{email}',))

def identify(request: Request):
    token = request.cookies.get('lhm_session')
    with connection() as db:
        if token:
            row = db.execute('''SELECT u.id,u.email,u.role,u.org_id,u.disabled,s.csrf
                 FROM sessions s JOIN users u ON u.id=s.user_id
                 WHERE s.hash=? AND s.expires_at>?''', (hash_secret(token),int(time.time()))).fetchone()
            if row and not row['disabled']:
                ident = dict(row); ident['auth_type']='browser'
                return ident
    raise HTTPException(401, 'Cần đăng nhập tài khoản nội bộ')

def require(*roles):
    def checker(request: Request, ident=Depends(identify)):
        if ident['role'] not in roles:
            raise HTTPException(403, 'Không đủ quyền')
        if request.method not in ('GET','HEAD'):
            if request.headers.get('x-csrf-token') != ident['csrf']:
                raise HTTPException(403, 'CSRF không hợp lệ')
        return ident
    return checker

def browser_admin(request: Request, ident=Depends(require('admin'))):
    if ident['auth_type'] != 'browser':
        raise HTTPException(403,'Phê duyệt chỉ được thực hiện qua phiên đăng nhập người quản trị')
    return ident

class Login(BaseModel):
    email: str
    password: str
    totp: str | None = None

@app.post('/api/login')
def login(data: Login, request: Request):
    ip = request.client.host if request.client else 'unknown'
    now = time.time()
    email = data.email.strip().lower()
    with connection() as db:
        if _login_blocked(db, email, ip, now):
            raise HTTPException(429,'Đăng nhập sai quá nhiều; thử lại sau 15 phút')
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if not user or user['disabled'] or not verify_password(user['password_hash'], data.password):
            _login_failed(db, email, ip, now)
            raise HTTPException(401,'Email hoặc mật khẩu không đúng')
        from .mfa import mfa_enabled, verify_user_totp
        if mfa_enabled(user['id']):
            if not data.totp:
                raise HTTPException(401,'mfa_required: Tài khoản đã bật MFA; nhập mã 6 số từ ứng dụng xác thực')
            if not verify_user_totp(user['id'], data.totp):
                _login_failed(db, email, ip, now)
                raise HTTPException(401,'Mã MFA không đúng')
        raw = make_secret()
        csrf = make_secret()
        db.execute('INSERT INTO sessions(hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                   (hash_secret(raw),user['id'],csrf,int(now)+86400))
        _login_succeeded(db, email)
        audit(db, dict(user),'auth.login','Browser session opened')
    from fastapi.responses import JSONResponse
    result = JSONResponse({'ok':True})
    result.set_cookie('lhm_session', raw, httponly=True, samesite='lax',
                      secure=os.environ.get('COOKIE_SECURE','true').lower()=='true', max_age=86400,
                      path='/')
    return result

@app.get('/api/me')
def me(ident=Depends(identify)):
    return {'email':ident['email'], 'role':ident['role'], 'org_id':ident['org_id'],
            'csrf':ident.get('csrf') if ident['auth_type']=='browser' else None}

@app.post('/api/logout')
def logout(request: Request, ident=Depends(require('admin','operator','reader'))):
    raw = request.cookies.get('lhm_session')
    with connection() as db:
        if raw:
            db.execute('DELETE FROM sessions WHERE hash=?',(hash_secret(raw),))
        audit(db, ident, 'auth.logout', 'Browser session closed')
    from fastapi.responses import JSONResponse
    result = JSONResponse({'ok':True})
    result.delete_cookie('lhm_session',path='/')
    return result

class CreateAccount(BaseModel):
    platform: Literal['demo','meta','tiktok','google','openai']
    label: str = Field(min_length=2,max_length=100)
    external_id: str = Field(min_length=2,max_length=120)
    currency: str = Field(default='VND',pattern=r'^[A-Z]{3}$')
    token: str = Field(default='',max_length=8192)

@app.get('/api/accounts')
def accounts(ident=Depends(require('admin','operator','reader'))):
    with connection() as db:
        rows = db.execute('''SELECT id,platform,label,external_id,currency,created_at,
                             CASE WHEN token_ciphertext IS NULL THEN 0 ELSE 1 END as connected
                             FROM accounts WHERE org_id=? ORDER BY id DESC''',(ident['org_id'],)).fetchall()
        return [dict(x) for x in rows]

@app.post('/api/accounts')
def create_account(data: CreateAccount, ident=Depends(require('admin'))):
    ext=data.external_id.strip()
    if data.platform != 'demo' and len(data.token)<12:
        raise HTTPException(422,'Cần token API được cấp chính thức; không nhập mật khẩu tài khoản')
    if data.platform=='meta' and not re.fullmatch(r'(act_)?\d{4,30}', ext):
        raise HTTPException(422,'ID tài khoản Meta phải là ID số hoặc act_ID')
    if data.platform=='demo' and data.token:
        raise HTTPException(422,'Tài khoản demo không lưu token')
    if data.platform=='google':
        try:
            bundle=json.loads(data.token)
            if not isinstance(bundle,dict) or not all(isinstance(bundle.get(f),str) and bundle[f] for f in ('client_id','client_secret','refresh_token')):
                raise ValueError('Missing required credentials')
        except (json.JSONDecodeError, ValueError, TypeError):
            raise HTTPException(422,'Google token phải là JSON có client_id, client_secret, refresh_token')
    if data.platform != 'demo' and not re.fullmatch(r'[A-Za-z0-9_\-]+', ext):
        raise HTTPException(422,'ID tài khoản chỉ được chứa ký tự chữ/số, - hoặc _')
    cipher=seal(data.token, f'acct:{ident["org_id"]}:{data.platform}:{ext}') if data.token else None
    with connection() as db:
        try:
            cur = db.execute('''INSERT INTO accounts (org_id,platform,label,external_id,currency,token_ciphertext)
                VALUES (?,?,?,?,?,?)''',(ident['org_id'],data.platform,data.label.strip(),ext,data.currency,cipher))
        except __import__('sqlite3').IntegrityError:
            raise HTTPException(409,'Tài khoản quảng cáo này đã tồn tại')
        audit(db, ident, 'account.create',f'{data.platform} account ID={cur.lastrowid}')
        return {'id':cur.lastrowid,'ok':True}

@app.delete('/api/accounts/{account_id}')
def remove_account(account_id:int, ident=Depends(require('admin'))):
    with connection() as db:
        item=db.execute('SELECT id FROM accounts WHERE id=? AND org_id=?',(account_id,ident['org_id'])).fetchone()
        if not item:
            raise HTTPException(404,'Không tìm thấy tài khoản')
        used=db.execute("SELECT COUNT(*) n FROM actions WHERE account_id=? AND status IN ('pending','executing')",(account_id,)).fetchone()['n']
        if used:
            raise HTTPException(409,'Tài khoản còn lệnh chờ duyệt')
        # Preserve audit and action references: revoke credentials and relabel instead of deleting.
        db.execute("UPDATE accounts SET token_ciphertext=NULL, label='[REVOKED] '||label WHERE id=?",(account_id,))
        audit(db,ident,'account.revoke',f'Account ID={account_id}; secret erased')
        return {'ok':True}

def get_account(account_id,org_id):
    with connection() as db:
        row=db.execute('SELECT * FROM accounts WHERE id=? AND org_id=?',(account_id,org_id)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy tài khoản')
        return dict(row)

@app.get('/api/report')
async def report(account_id:int, period:str='last_7d',
                 date_from:str|None=None, date_to:str|None=None,
                 ident=Depends(require('admin','operator','reader'))):
    first,last=resolve_date_range(period,date_from,date_to)
    result=await fetch_report(get_account(account_id,ident['org_id']),'custom',first,last)
    return result

@app.get('/api/summary')
async def summary(period:str='last_7d',date_from:str|None=None,date_to:str|None=None,
                  ident=Depends(require('admin','operator','reader'))):
    """Tenant-scoped reports. Demo is never added to real Ads totals.

    All active accounts are included; concurrent provider calls are bounded to
    protect local memory and avoid unbounded bursts against provider APIs.
    """
    first,last=resolve_date_range(period,date_from,date_to)
    with connection() as db:
        accs=[dict(x) for x in db.execute(
            'SELECT * FROM accounts WHERE org_id=? AND label NOT LIKE ? ORDER BY id',
            (ident['org_id'],'[REVOKED]%')).fetchall()]
    semaphore=asyncio.Semaphore(5)

    async def one(a):
        async with semaphore:
            try:
                return {'account_id':a['id'],'label':a['label'],'platform':a['platform'],
                        'result':await fetch_report(a,'custom',first,last)}
            except HTTPException as exc:
                return {'account_id':a['id'],'label':a['label'],'platform':a['platform'],
                        'error':str(exc.detail)}
            except Exception:
                # Do not expose token contents or third-party exception bodies.
                return {'account_id':a['id'],'label':a['label'],'platform':a['platform'],
                        'error':'Không lấy được báo cáo. Kiểm tra kết nối và nhật ký ứng dụng.'}

    items=await asyncio.gather(*(one(a) for a in accs))
    succeeded=[x['result'] for x in items if 'result' in x]
    live=[x for x in succeeded if x['source']!='demo']
    demo=[x for x in succeeded if x['source']=='demo']
    # Preview Demo only when there are NO real accounts at all, including
    # failed real connections. Otherwise never silently replace real with fake.
    demo_only=bool(demo) and not any(a['platform']!='demo' for a in accs)
    included=demo if demo_only else live
    currency_groups={}
    for record in included:
        currency=record['currency']
        group=currency_groups.setdefault(currency,[])
        group.append(record)
    by_currency={}
    for currency, group in sorted(currency_groups.items()):
        by_currency[currency]={
            'spend':round(sum(x['spend'] for x in group),2),
            'clicks':sum(x['clicks'] for x in group),
            'impressions':sum(x['impressions'] for x in group),
            'accounts':len(group)}
    clicks=sum(x['clicks'] for x in included)
    impressions=sum(x['impressions'] for x in included)
    single_currency=next(iter(by_currency)) if len(by_currency)==1 else None
    # Conversion metrics are comparable only when every included provider
    # returned them for the SAME conversion definition. Unknown is NOT zero.
    definitions={x.get('conversion_action_type') for x in included}
    known_conversions=bool(included) and all(x.get('conversions') is not None for x in included) and len(definitions)==1
    conversions=round(sum(float(x['conversions']) for x in included),2) if known_conversions else None
    known_values=known_conversions and all(x.get('conversion_value') is not None for x in included)
    conversion_value=round(sum(float(x['conversion_value']) for x in included),2) if known_values and single_currency else None
    spend=by_currency[single_currency]['spend'] if single_currency else None
    totals={
        'spend':spend,'currency':single_currency,
        'impressions':impressions,'clicks':clicks,
        'ctr':round(100*clicks/impressions,2) if impressions else 0,
        'contains_demo':demo_only,
        'has_demo_accounts':bool(demo),
        'data_mode':'demo' if demo_only else 'live',
        'included_accounts':len(included),
        'total_accounts':len(accs),
        'failed_accounts':sum('error' in x for x in items),
        'by_currency':by_currency,
        'conversions':conversions,
        'conversion_value':conversion_value,
        'conversion_action_type':next(iter(definitions)) if known_conversions else None,
        'cpa':round(spend/conversions,2) if spend is not None and conversions and conversions>0 else None,
        'roas':round(conversion_value/spend,2) if conversion_value is not None and spend and spend>0 else None,
        'sources':sorted({x['source'] for x in included})}
    return {'period':period,'date_from':first,'date_to':last,'totals':totals,'accounts':items,
            'note':'Tách Demo khỏi tổng số liệu thật; giới hạn đồng thời 5 nguồn API và không tự gán chỉ số chuyển đổi.'}

class ActionRequest(BaseModel):
    account_id: int
    campaign_id: str = Field(min_length=5,max_length=30)

@app.post('/api/actions')
def request_pause(data:ActionRequest, ident=Depends(require('admin','operator'))):
    acc=get_account(data.account_id,ident['org_id'])
    if acc['platform'] not in ('meta','google'):
        raise HTTPException(422,'Chỉ tạm dừng chiến dịch Google Ads hoặc Meta Ads')
    if not re.fullmatch(r'\d{5,30}',data.campaign_id):
        raise HTTPException(422,'ID chiến dịch không hợp lệ')
    with connection() as db:
        cur=db.execute('''INSERT INTO actions(org_id,account_id,action_type,target_id,requested_by)
            VALUES (?,?,?,?,?)''',(ident['org_id'],acc['id'],'pause_campaign',data.campaign_id,ident['id']))
        audit(db,ident,'action.request',f'Pause requested #{cur.lastrowid} for account {acc["id"]}')
        return {'id':cur.lastrowid,'status':'pending','message':'Chờ quản trị viên xác nhận trên website'}

@app.get('/api/actions')
def list_actions(ident=Depends(require('admin','operator','reader'))):
    with connection() as db:
        rows=db.execute('''SELECT a.id,a.account_id,a.action_type,a.target_id,a.status,a.created_at,
                         a.reviewed_at,a.failure_reason,acc.label as account_label,acc.platform as platform
                         FROM actions a JOIN accounts acc ON acc.id=a.account_id
                         WHERE a.org_id=? ORDER BY a.id DESC LIMIT 100''',(ident['org_id'],)).fetchall()
        return [dict(x) for x in rows]

async def notify_telegram(message):
    token=os.environ.get('TELEGRAM_BOT_TOKEN','')
    chat_id=os.environ.get('TELEGRAM_CHAT_ID','')
    if token and chat_id:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f'https://api.telegram.org/bot{token}/sendMessage',
                                  json={'chat_id':chat_id,'text':message})
        except httpx.HTTPError:
            pass

@app.post('/api/actions/{action_id}/approve')
async def approve(action_id:int, ident=Depends(browser_admin)):
    with connection() as db:
        row=db.execute('''SELECT a.*,acc.platform,acc.external_id,acc.token_ciphertext,acc.currency,acc.label
                        FROM actions a JOIN accounts acc ON acc.id=a.account_id
                        WHERE a.id=? AND a.org_id=?''',(action_id,ident['org_id'])).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy lệnh')
        if row['status']!='pending':
            raise HTTPException(409,'Lệnh đã được xử lý')
        from .licensing import license_required
        license_required()
        cur=db.execute("UPDATE actions SET status='executing',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                       (ident['id'],action_id))
        if cur.rowcount!=1:
            raise HTTPException(409,'Lệnh đã được người khác xử lý')
        audit(db,ident,'action.approve',f'Approved action #{action_id}')
        acc=dict(row); acc['org_id']=ident['org_id']
    try:
        if acc['platform']=='google':
            from .google_mutations import pause_google_campaign
            await pause_google_campaign(acc,row['target_id'])
        elif acc['platform']=='meta':
            await pause_meta_campaign(acc,row['target_id'])
        else:
            raise HTTPException(422,'Nền tảng quảng cáo không hỗ trợ thao tác này')
    except HTTPException as exc:
        with connection() as db:
            db.execute('UPDATE actions SET status=?, failure_reason=? WHERE id=?',('failed',str(exc.detail)[:180],action_id))
            audit(db,ident,'action.failed',f'Action #{action_id} failed')
        raise
    with connection() as db:
        db.execute('UPDATE actions SET status=? WHERE id=?',('completed',action_id))
        audit(db,ident,'action.completed',f'Action #{action_id} completed')
    await notify_telegram(f'LHM Ads AI: API {acc["platform"]} chấp nhận tạm dừng campaign {row["target_id"]} (account #{row["account_id"]}).')
    return {'ok':True,'status':'completed'}

@app.post('/api/actions/{action_id}/reject')
def reject(action_id:int, ident=Depends(browser_admin)):
    with connection() as db:
        cur=db.execute('''UPDATE actions SET status='rejected',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP
                   WHERE id=? AND org_id=? AND status='pending' ''',(ident['id'],action_id,ident['org_id']))
        if cur.rowcount!=1:
            raise HTTPException(409,'Không tìm thấy lệnh chờ duyệt')
        audit(db,ident,'action.reject',f'Rejected action #{action_id}')
        return {'ok':True}

@app.get('/api/audit')
def audit_feed(ident=Depends(require('admin'))):
    with connection() as db:
        rows=db.execute('''SELECT id,actor_id,event,detail,created_at FROM audit WHERE org_id=?
                           ORDER BY id DESC LIMIT 100''',(ident['org_id'],)).fetchall()
        return [dict(r) for r in rows]
