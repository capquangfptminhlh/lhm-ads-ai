"""First-party OAuth connect flows for Google Ads / Meta Ads. NO MCP.

Credentials never reach the browser. Authorization requests are session-bound,
one-time, expiring and all provider URLs are fixed (no dynamic URLs or redirects).
"""
import base64
import hashlib
import json
import os
import re
import secrets
import time
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .app import app, browser_admin
from .db import audit, connection
from .security import hash_secret, seal, unseal

GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
META_AUTH = 'https://www.facebook.com/{version}/dialog/oauth'
META_API = 'https://graph.facebook.com/{version}'
GOOGLE_SCOPE = 'https://www.googleapis.com/auth/adwords'
TTL = 600
ID_PATTERN = re.compile(r'^\d{4,30}$')


def init_oauth_tables():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS oauth_flows (
            state_hash TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            session_hash TEXT NOT NULL,
            provider TEXT NOT NULL,
            verifier_ciphertext TEXT,
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS oauth_pending (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            session_hash TEXT NOT NULL,
            provider TEXT NOT NULL,
            credential_ciphertext TEXT NOT NULL,
            candidates_json TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        );
        ''')
        # Expired OAuth secrets should not remain indefinitely, even after failures.
        db.execute('DELETE FROM oauth_flows WHERE expires_at < ?', (int(time.time()),))
        db.execute('DELETE FROM oauth_pending WHERE expires_at < ?', (int(time.time()),))


def app_origin():
    base = os.getenv('PUBLIC_BASE_URL', 'http://127.0.0.1:8765').strip().rstrip('/')
    # Exact configured origin only: never use untrusted Host or X-Forwarded-* headers.
    from urllib.parse import urlsplit
    parts = urlsplit(base)
    if parts.username or parts.password or parts.query or parts.fragment or (parts.path not in ('', '/')):
        raise HTTPException(503, 'PUBLIC_BASE_URL phải là origin, không có đường dẫn hoặc tham số')
    if parts.scheme == 'https' and parts.hostname and parts.port != 0:
        return base
    if parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1'):
        return base
    raise HTTPException(503, 'OAuth yêu cầu HTTPS hoặc localhost; cấu hình PUBLIC_BASE_URL')


def provider_config(provider,org_id=None):
    from .desktop_setup import desktop_mode, desktop_provider
    if desktop_mode():
        cfg=desktop_provider(org_id or "main",provider)
        if not cfg:
            return "", "", False
        cid,secret=cfg["client_id"],cfg["client_secret"]
        return cid,secret,bool(cid and (provider=="google" or secret))
    if provider == 'google':
        cid = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '').strip()
        secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
        return cid, secret, bool(cid and secret) # legacy server-side web flow
    if provider == 'meta':
        cid = os.getenv('META_APP_ID', '').strip()
        secret = os.getenv('META_APP_SECRET', '').strip()
        return cid, secret, bool(cid and secret)
    raise HTTPException(404, 'Nền tảng OAuth không được hỗ trợ')


def callback_url(provider):
    return f'{app_origin()}/api/oauth/{provider}/callback'


def session_hash(request):
    cookie = request.cookies.get('lhm_session', '')
    if not cookie:
        raise HTTPException(401, 'Cần đăng nhập')
    return hash_secret(cookie)


@app.get('/api/oauth/status')
def oauth_status(ident=Depends(browser_admin)):
    return {
        'google': {'configured':provider_config('google',ident['org_id'])[2],
                   'callback_url':callback_url('google'),
                   'requires':'Google OAuth Desktop Client on this computer; API access is tied to the Google Cloud project'},
        'meta': {'configured':provider_config('meta',ident['org_id'])[2],
                 'callback_url':callback_url('meta'),
                 'requires':'Meta App + ads_read; localhost OAuth may only work in Development mode'},
    }


@app.post('/api/oauth/{provider}/start')
def start_oauth(provider: Literal['google','meta'], request: Request, ident=Depends(browser_admin)):
    client_id, _, ready = provider_config(provider,ident['org_id'])
    if not ready:
        raise HTTPException(422, f'{provider.upper()}: chưa cấu hình thông tin ứng dụng OAuth trên máy chủ')
    init_oauth_tables()
    state = secrets.token_urlsafe(32)
    state_hash = hash_secret(state)
    verifier = secrets.token_urlsafe(64) if provider == 'google' else ''
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=') if verifier else ''
    encrypted = seal(verifier, f'oauth-flow:{state_hash}') if verifier else None
    with connection() as db:
        db.execute('INSERT INTO oauth_flows VALUES (?,?,?,?,?,?,?)',
                   (state_hash, ident['org_id'], ident['id'], session_hash(request), provider, encrypted, int(time.time())+TTL))
        audit(db, ident, 'oauth.start', f'{provider} consent started')
    redirect_uri = callback_url(provider)
    if provider == 'google':
        url = GOOGLE_AUTH + '?' + urlencode({
            'client_id':client_id, 'redirect_uri':redirect_uri, 'response_type':'code',
            'scope':GOOGLE_SCOPE, 'access_type':'offline', 'prompt':'consent',
            'code_challenge':challenge, 'code_challenge_method':'S256', 'state':state,
        })
    else:
        version=os.getenv('META_GRAPH_VERSION','v24.0')
        if not re.fullmatch(r'v\d+\.\d+',version):
            raise HTTPException(503,'META_GRAPH_VERSION không hợp lệ')
        scopes=os.getenv('META_OAUTH_SCOPES','ads_read')
        if scopes not in ('ads_read','ads_read,ads_management'):
            raise HTTPException(503,'META_OAUTH_SCOPES không hợp lệ')
        url = META_AUTH.format(version=version) + '?' + urlencode({
            'client_id':client_id,'redirect_uri':redirect_uri,'response_type':'code',
            'scope':scopes,'state':state,
        })
    return {'authorization_url':url}


def redirect_status(value):
    return RedirectResponse('/studio?oauth='+value, status_code=303,
                            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


async def google_exchange(client, code, redirect_uri, verifier, cid, secret):
    token_data={'client_id':cid,'code':code,'grant_type':'authorization_code',
        'redirect_uri':redirect_uri,'code_verifier':verifier}
    if secret: token_data['client_secret']=secret
    res=await client.post(GOOGLE_TOKEN,data=token_data)
    res.raise_for_status()
    tokens=res.json()
    if not isinstance(tokens,dict) or not tokens.get('refresh_token') or not tokens.get('access_token'):
        raise ValueError('Google không cấp refresh token; hãy thu hồi quyền ứng dụng và đăng nhập lại')
    return tokens


async def google_candidates(client, access_token):
    # Developer tokens were sunset for Google Ads API (Sep 2026). Legacy header is optional.
    devtoken=os.environ.get('GOOGLE_ADS_DEVELOPER_TOKEN','')
    version=os.getenv('GOOGLE_ADS_API_VERSION','v25')
    if not re.fullmatch(r'v\d+', version):
        raise ValueError('Google Ads API version không hợp lệ')
    headers={'Authorization':'Bearer '+access_token}
    if devtoken: headers['developer-token']=devtoken
    url=f'https://googleads.googleapis.com/{version}/customers:listAccessibleCustomers'
    res=await client.get(url, headers=headers)
    res.raise_for_status()
    roots=res.json().get('resourceNames',[])
    if not isinstance(roots,list):
        raise ValueError('Malformed listAccessibleCustomers')
    accounts = {}
    for name in roots[:30]:
        if not isinstance(name,str) or not re.fullmatch(r'customers/\d{8,20}',name):
            continue
        cid=name.split('/')[-1]
        accounts[cid]={'id':cid,'label':f'Google Ads {cid}', 'currency':'XXX', 'login_customer_id':''}
        # Manager account children (customer_client), with the manager ID saved for subsequent GAQL calls.
        try:
            r=await client.post(f'https://googleads.googleapis.com/{version}/customers/{cid}/googleAds:searchStream',
                                headers=headers,json={'query':('SELECT customer_client.id, customer_client.descriptive_name, '
                                    'customer_client.currency_code, customer_client.manager '
                                    'FROM customer_client WHERE customer_client.status = ENABLED LIMIT 200')})
            if r.status_code != 200:
                continue
            for page in r.json():
                for item in page.get('results',[]):
                    c=item.get('customerClient') or {}
                    child=str(c.get('id',''))
                    if not re.fullmatch(r'\d{8,20}',child):
                        continue
                    label=str(c.get('descriptiveName') or f'Google Ads {child}')[:90]
                    cur=str(c.get('currencyCode') or 'XXX')
                    cur=cur if re.fullmatch(r'[A-Z]{3}',cur) else 'XXX'
                    if child==cid:
                        accounts[child].update(label=label,currency=cur)
                    elif child not in accounts:
                        accounts[child]={'id':child,'label':label,'currency':cur,'login_customer_id':cid}
        except (httpx.HTTPError,ValueError,TypeError,KeyError):
            pass  # Listing direct accounts still works; do not fabricate currency.
    return list(accounts.values())[:200]


async def meta_exchange(client,code,redirect_uri,cid,secret):
    version=os.getenv('META_GRAPH_VERSION','v24.0')
    base=META_API.format(version=version)
    exchange=await client.get(base+'/oauth/access_token', params={
        'client_id':cid,'client_secret':secret,'redirect_uri':redirect_uri,'code':code})
    exchange.raise_for_status()
    short=exchange.json().get('access_token')
    if not isinstance(short,str) or not short:
        raise ValueError('Meta không trả access token')
    long=await client.get(base+'/oauth/access_token',params={
        'grant_type':'fb_exchange_token','client_id':cid,'client_secret':secret,'fb_exchange_token':short})
    long.raise_for_status()
    token=long.json().get('access_token')
    if not isinstance(token,str) or not token:
        raise ValueError('Meta không cấp long-lived token')
    return token


async def meta_candidates(client, token):
    base=META_API.format(version=os.getenv('META_GRAPH_VERSION','v24.0'))
    results=[]
    after=None
    for _ in range(5):
        params={'fields':'id,name,currency,account_status','limit':100}
        if after:params['after']=after
        r=await client.get(base+'/me/adaccounts',params=params,headers={'Authorization':'Bearer '+token})
        r.raise_for_status()
        data=r.json()
        for item in data.get('data',[]):
            acc=str(item.get('id','')).replace('act_','')
            if not ID_PATTERN.fullmatch(acc):continue
            cur=str(item.get('currency') or 'XXX')
            results.append({'id':'act_'+acc,'label':str(item.get('name') or f'Meta Ads {acc}')[:90],
                            'currency':cur if re.fullmatch(r'[A-Z]{3}',cur) else 'XXX'})
        after=(data.get('paging',{}).get('cursors') or {}).get('after')
        if not after or len(results)>=300:break
    return results[:300]


@app.get('/api/oauth/{provider}/callback',include_in_schema=False)
async def oauth_callback(provider: Literal['google','meta'], request:Request,
                         state:str='',code:str='',error:str=''):
    # Cookie is SameSite=Lax: top-level provider -> callback redirects include session.
    from .app import identify
    ident=identify(request)
    if ident['role']!='admin':
        raise HTTPException(403,'Chỉ admin có quyền kết nối quảng cáo')
    if not state or len(state)>256:
        raise HTTPException(400,'OAuth state không hợp lệ')
    init_oauth_tables()
    state_hash=hash_secret(state)
    with connection() as db:
        row=db.execute('SELECT * FROM oauth_flows WHERE state_hash=?', (state_hash,)).fetchone()
        # Consume exactly once BEFORE exchanging tokens.
        db.execute('DELETE FROM oauth_flows WHERE state_hash=?',(state_hash,))
        if not row or row['expires_at']<=int(time.time()) or row['provider']!=provider or row['org_id']!=ident['org_id'] or row['user_id']!=ident['id'] or row['session_hash']!=session_hash(request):
            raise HTTPException(400,'OAuth state hết hạn hoặc không thuộc phiên đăng nhập')
    if error or not code or len(code)>4096:
        return redirect_status('cancelled')
    cid, secret, ready=provider_config(provider,ident['org_id'])
    if not ready:
        return redirect_status('error')
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25,connect=8),trust_env=False) as client:
            if provider=='google':
                verifier=unseal(row['verifier_ciphertext'],f'oauth-flow:{state_hash}')
                creds=await google_exchange(client,code,callback_url(provider),verifier,cid,secret)
                candidates=await google_candidates(client,creds['access_token'])
                private=json.dumps({'client_id':cid,'client_secret':secret,'refresh_token':creds['refresh_token']})
            else:
                private=await meta_exchange(client,code,callback_url(provider),cid,secret)
                candidates=await meta_candidates(client,private)
        if not candidates:
            return redirect_status('no_accounts')
    except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError):
        return redirect_status('provider_error')
    pending_id=secrets.token_urlsafe(24)
    with connection() as db:
        db.execute('INSERT INTO oauth_pending VALUES (?,?,?,?,?,?,?,?)',
                   (pending_id,ident['org_id'],ident['id'],session_hash(request),provider,
                    seal(private,f'oauth-pending:{pending_id}'),json.dumps(candidates),int(time.time())+TTL))
        audit(db,ident,'oauth.ready',f'{provider}: {len(candidates)} accounts discovered; awaiting selection')
    return redirect_status('ready')


@app.get('/api/oauth/pending')
def pending_oauth(request:Request, ident=Depends(browser_admin)):
    init_oauth_tables()
    with connection() as db:
        rows=db.execute('''SELECT id,provider,candidates_json,expires_at FROM oauth_pending
                          WHERE org_id=? AND user_id=? AND session_hash=? AND expires_at>?
                          ORDER BY expires_at DESC LIMIT 5''',
                        (ident['org_id'],ident['id'],session_hash(request),int(time.time()))).fetchall()
    return [{'id':r['id'],'provider':r['provider'],'accounts':json.loads(r['candidates_json']),
             'expires_at':r['expires_at']} for r in rows]


class ImportSelection(BaseModel):
    account_ids: list[str] = Field(min_length=1,max_length=200)


@app.post('/api/oauth/pending/{pending_id}/import')
def import_oauth(pending_id:str, selection:ImportSelection, request:Request,
                 ident=Depends(browser_admin)):
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',pending_id):
        raise HTTPException(404,'Không có kết nối đang chờ')
    init_oauth_tables()
    if len(set(selection.account_ids))!=len(selection.account_ids):
        raise HTTPException(422,'Danh sách tài khoản trùng nhau')
    with connection() as db:
        row=db.execute('''SELECT * FROM oauth_pending WHERE id=? AND org_id=? AND user_id=?
                          AND session_hash=? AND expires_at>?''',
                       (pending_id, ident['org_id'],ident['id'],session_hash(request),int(time.time()))).fetchone()
        if not row:
            raise HTTPException(404,'Kết nối hết hạn hoặc không thuộc phiên đăng nhập')
        choices={a['id']:a for a in json.loads(row['candidates_json'])}
        if not set(selection.account_ids).issubset(choices):
            raise HTTPException(422,'Không thể kết nối tài khoản ngoài danh sách được cấp quyền')
        secret=unseal(row['credential_ciphertext'],f'oauth-pending:{pending_id}')
        provider=row['provider']
        count=0
        for external_id in selection.account_ids:
            candidate=choices[external_id]
            account_secret=secret
            if provider=='google':
                credential=json.loads(secret)
                credential['login_customer_id']=candidate.get('login_customer_id','')
                account_secret=json.dumps(credential)
            encrypted=seal(account_secret,f'acct:{ident["org_id"]}:{provider}:{external_id}')
            db.execute('''INSERT INTO accounts(org_id,platform,label,external_id,currency,token_ciphertext)
                VALUES(?,?,?,?,?,?) ON CONFLICT(org_id,platform,external_id) DO UPDATE SET
                label=excluded.label,currency=excluded.currency,token_ciphertext=excluded.token_ciphertext''',
                       (ident['org_id'],provider,candidate['label'],external_id,candidate['currency'],encrypted))
            count+=1
        db.execute('DELETE FROM oauth_pending WHERE id=?',(pending_id,))
        audit(db,ident,'oauth.import',f'{provider}: {count} authorized ad accounts imported')
    return {'ok':True,'imported':count,'provider':provider}


@app.delete('/api/oauth/pending/{pending_id}')
def dismiss_oauth(pending_id:str,request:Request,ident=Depends(browser_admin)):
    init_oauth_tables()
    with connection() as db:
        db.execute('DELETE FROM oauth_pending WHERE id=? AND org_id=? AND user_id=? AND session_hash=?',
                   (pending_id,ident['org_id'],ident['id'],session_hash(request)))
    return {'ok':True}
