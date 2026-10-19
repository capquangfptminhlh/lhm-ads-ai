"""LHM Ads AI: login, tenant-bound accounts, reporting and human-approved changes."""
import os
import re
import time
import json
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import connection, init_db, audit
from .security import (hash_secret, make_secret, verify_password, seal, validate_secrets)
from .providers import fetch_report, pause_meta_campaign

@asynccontextmanager
async def lifespan(application):
    validate_secrets()
    init_db()
    yield

app = FastAPI(title='LHM Ads AI Starter', docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount('/static', StaticFiles(directory=str(Path(__file__).resolve().parent.parent/'static')), name='static')

@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'none'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    return response

@app.get('/')
async def home():
    return FileResponse(str(Path(__file__).resolve().parent.parent/'static'/'index.html'))

@app.get('/healthz')
async def health():
    return {'ok':True}

# Replace memory login throttling with proxy/WAF or Redis rate limits for multiple instances.
login_failures = defaultdict(list)

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

@app.post('/api/login')
def login(data: Login, request: Request):
    ip = request.client.host if request.client else 'unknown'
    now = time.time()
    login_failures[ip] = [t for t in login_failures[ip] if now-t<300]
    if len(login_failures[ip]) >= 5:
        raise HTTPException(429,'Đăng nhập sai quá nhiều; thử lại sau 5 phút')
    with connection() as db:
        user = db.execute('SELECT * FROM users WHERE email=?', (data.email.strip().lower(),)).fetchone()
        if not user or user['disabled'] or not verify_password(user['password_hash'], data.password):
            login_failures[ip].append(now)
            raise HTTPException(401,'Email hoặc mật khẩu không đúng')
        raw = make_secret()
        csrf = make_secret()
        db.execute('INSERT INTO sessions(hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                   (hash_secret(raw),user['id'],csrf,int(now)+86400))
        login_failures[ip] = []
        audit(db, dict(user),'auth.login','Browser session opened')
    from fastapi.responses import JSONResponse
    result = JSONResponse({'ok':True})
    result.set_cookie('lhm_session', raw, httponly=True, samesite='strict',
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
async def report(account_id:int, period:Literal['last_7d','yesterday']='last_7d',
                 ident=Depends(require('admin','operator','reader'))):
    result=await fetch_report(get_account(account_id,ident['org_id']),period)
    return result

@app.get('/api/summary')
async def summary(period:Literal['last_7d','yesterday']='last_7d', ident=Depends(require('admin','operator','reader'))):
    with connection() as db:
        accs=[dict(x) for x in db.execute('SELECT * FROM accounts WHERE org_id=? AND label NOT LIKE ?',
                                          (ident['org_id'],'[REVOKED]%')).fetchall()][:20]
    async def one(a):
        try:
            return {'account_id':a['id'],'label':a['label'],'platform':a['platform'],
                    'result':await fetch_report(a,period)}
        except HTTPException as exc:
            return {'account_id':a['id'],'label':a['label'],'platform':a['platform'],
                    'error':exc.detail}
    items=await asyncio.gather(*(one(a) for a in accs))
    ok=[x['result'] for x in items if 'result' in x]
    currencies={x['currency'] for x in ok}
    impressions=sum(x['impressions'] for x in ok)
    clicks=sum(x['clicks'] for x in ok)
    totals={'spend':round(sum(x['spend'] for x in ok),2) if len(currencies)==1 else None,
            'currency':next(iter(currencies)) if len(currencies)==1 else None,
            'impressions':impressions,'clicks':clicks,
            'ctr':round(100*clicks/impressions,2) if impressions else 0,
            'contains_demo':any(x['source']=='demo' for x in ok),
            'sources':sorted({x['source'] for x in ok})}
    return {'period':period,'totals':totals,'accounts':items,
            'note':'Chỉ tổng hợp tối đa 20 tài khoản ở MVP; không cộng tiền giữa nhiều loại tiền tệ.'}

class ActionRequest(BaseModel):
    account_id: int
    campaign_id: str = Field(min_length=5,max_length=30)

@app.post('/api/actions')
def request_pause(data:ActionRequest, ident=Depends(require('admin','operator'))):
    acc=get_account(data.account_id,ident['org_id'])
    if acc['platform']!='meta':
        raise HTTPException(422,'Chỉ thao tác tạm dừng chiến dịch Meta trong phiên bản nền tảng')
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
                         a.reviewed_at,a.failure_reason,acc.label as account_label
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
        cur=db.execute("UPDATE actions SET status='executing',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                       (ident['id'],action_id))
        if cur.rowcount!=1:
            raise HTTPException(409,'Lệnh đã được người khác xử lý')
        audit(db,ident,'action.approve',f'Approved action #{action_id}')
        acc=dict(row); acc['org_id']=ident['org_id']
    try:
        await pause_meta_campaign(acc,row['target_id'])
    except HTTPException as exc:
        with connection() as db:
            db.execute('UPDATE actions SET status=?, failure_reason=? WHERE id=?',('failed',str(exc.detail)[:180],action_id))
            audit(db,ident,'action.failed',f'Action #{action_id} failed')
        raise
    with connection() as db:
        db.execute('UPDATE actions SET status=? WHERE id=?',('completed',action_id))
        audit(db,ident,'action.completed',f'Action #{action_id} completed')
    await notify_telegram(f'LHM Ads AI: Admin duyệt và tạm dừng Meta campaign {row["target_id"]} (account #{row["account_id"]}).')
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
