"""Opt-in daily spend thresholds and secure Web Push delivery.

Read-only: never mutates Ads. Requires an independently running agent/service
and valid provider API access; a PWA alone cannot monitor in the background.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import time
from datetime import date
from urllib.parse import urlparse

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from .app import app, browser_admin, require
from .db import connection, audit
from .security import seal, unseal

def init_push_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS budget_rules (
          org_id TEXT NOT NULL, account_id INTEGER NOT NULL REFERENCES accounts(id),
          threshold REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
          updated_at INTEGER NOT NULL, PRIMARY KEY(org_id,account_id)
        );
        CREATE TABLE IF NOT EXISTS budget_events (
          org_id TEXT NOT NULL, account_id INTEGER NOT NULL REFERENCES accounts(id),
          day TEXT NOT NULL, created_at INTEGER NOT NULL,
          spend REAL NOT NULL, threshold REAL NOT NULL, currency TEXT NOT NULL,
          PRIMARY KEY(org_id,account_id,day)
        );
        CREATE TABLE IF NOT EXISTS push_subscriptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          org_id TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          endpoint_hash TEXT NOT NULL UNIQUE, sealed TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_push_org ON push_subscriptions(org_id);
        """)

class BudgetRuleInput(BaseModel):
    threshold: float = Field(gt=0,le=1000000000000)
    enabled: bool = True

@app.get('/api/budgets')
def list_budgets(ident=Depends(require('admin','operator','reader'))):
    init_push_db()
    with connection() as db:
        rows=db.execute("""SELECT a.id account_id,a.label,a.platform,a.currency,
          r.threshold,COALESCE(r.enabled,0) enabled
          FROM accounts a LEFT JOIN budget_rules r ON r.account_id=a.id AND r.org_id=a.org_id
          WHERE a.org_id=? AND a.platform IN ('google','meta') AND a.token_ciphertext IS NOT NULL
          AND a.label NOT LIKE '[REVOKED]%' ORDER BY a.id""",(ident['org_id'],)).fetchall()
    return {'rules':[dict(r) for r in rows],
            'note':'Spend TODAY được báo cáo bởi tài khoản Ads, có thể trễ và khác múi giờ máy chủ.'}

@app.put('/api/budgets/{account_id}')
def save_budget(account_id:int, body:BudgetRuleInput, ident=Depends(browser_admin)):
    init_push_db()
    with connection() as db:
        acc=db.execute("""SELECT id,platform,currency FROM accounts WHERE id=? AND org_id=?
          AND token_ciphertext IS NOT NULL AND label NOT LIKE '[REVOKED]%'""",
          (account_id,ident['org_id'])).fetchone()
        if not acc or acc['platform'] not in ('google','meta'):
            raise HTTPException(404,'Không tìm thấy tài khoản quảng cáo đã kết nối')
        db.execute("""INSERT INTO budget_rules(org_id,account_id,threshold,enabled,updated_at)
          VALUES(?,?,?,?,?) ON CONFLICT(org_id,account_id) DO UPDATE
          SET threshold=excluded.threshold,enabled=excluded.enabled,updated_at=excluded.updated_at""",
          (ident['org_id'],account_id,body.threshold,int(body.enabled),int(time.time())))
        audit(db,ident,'budget.rule',f'Account #{account_id} enabled={body.enabled} ({acc["currency"]})')
    return {'ok':True,'account_id':account_id,'threshold':body.threshold,
            'currency':acc['currency'],'enabled':body.enabled}

def push_available():
    path=os.environ.get('LHM_VAPID_PRIVATE_KEY_FILE','')
    pub=os.environ.get('LHM_VAPID_PUBLIC_KEY','')
    subject=os.environ.get('LHM_VAPID_SUBJECT','')
    return bool(path and os.path.isfile(path) and pub and subject.startswith(('mailto:','https://')))

@app.get('/api/push/config')
def push_config(ident=Depends(require('admin','operator','reader'))):
    return {'available':push_available(),
            'public_key':os.environ.get('LHM_VAPID_PUBLIC_KEY','') if push_available() else '',
            'note':'Cần HTTPS, quyền thông báo và dịch vụ giám sát chạy liên tục.'}

class SubscriptionInput(BaseModel):
    endpoint: str = Field(min_length=35,max_length=2048)
    keys: dict[str,str]

def _safe_endpoint(endpoint):
    try:
        url=urlparse(endpoint)
        host=(url.hostname or '').lower()
        port=url.port
    except ValueError:
        return False
    # Explicit allowlist prevents server-side request forgery by malicious subscriptions.
    return url.scheme=='https' and port in (None,443) and not url.username and not url.password and (
        host=='fcm.googleapis.com' or host=='updates.push.services.mozilla.com'
        or host=='push.services.mozilla.com' or host=='web.push.apple.com'
        or host.endswith('.push.apple.com'))

@app.post('/api/push/subscriptions')
def subscribe(body:SubscriptionInput, ident=Depends(require('admin','operator','reader'))):
    if not push_available():
        raise HTTPException(503,'Chưa cấu hình Web Push VAPID trên máy chủ')
    if not _safe_endpoint(body.endpoint):
        raise HTTPException(422,'Push endpoint không thuộc nhà cung cấp được hỗ trợ')
    for k in ('p256dh','auth'):
        val=body.keys.get(k,'')
        if not isinstance(val,str) or len(val)<10 or len(val)>256:
            raise HTTPException(422,'Không có khóa Push mã hóa hợp lệ')
    init_push_db()
    digest=hashlib.sha256(body.endpoint.encode()).hexdigest()
    payload=json.dumps({'endpoint':body.endpoint,'keys':{
         'p256dh':body.keys['p256dh'],'auth':body.keys['auth']}},separators=(',',':'))
    ciphertext=seal(payload,'push:'+digest)
    with connection() as db:
        existing=db.execute('SELECT org_id,user_id FROM push_subscriptions WHERE endpoint_hash=?',(digest,)).fetchone()
        if existing and (existing['org_id']!=ident['org_id'] or existing['user_id']!=ident['id']):
            raise HTTPException(409,'Thiết bị đã được đăng ký cho người dùng khác')
        count=db.execute('SELECT COUNT(*) c FROM push_subscriptions WHERE user_id=?',(ident['id'],)).fetchone()['c']
        if not existing and count>=5:
            raise HTTPException(409,'Tối đa 5 thiết bị thông báo mỗi người dùng')
        db.execute("""INSERT INTO push_subscriptions(org_id,user_id,endpoint_hash,sealed,created_at)
          VALUES(?,?,?,?,?) ON CONFLICT(endpoint_hash) DO UPDATE SET sealed=excluded.sealed""",
          (ident['org_id'],ident['id'],digest,ciphertext,int(time.time())))
        audit(db,ident,'push.subscribe','Enabled Web Push on a user device')
    return {'ok':True}

@app.delete('/api/push/subscriptions')
def unsubscribe(body:SubscriptionInput, ident=Depends(require('admin','operator','reader'))):
    digest=hashlib.sha256(body.endpoint.encode()).hexdigest()
    init_push_db()
    with connection() as db:
        db.execute('DELETE FROM push_subscriptions WHERE user_id=? AND org_id=? AND endpoint_hash=?',
                   (ident['id'],ident['org_id'],digest))
        audit(db,ident,'push.unsubscribe','Disabled Web Push on a user device')
    return {'ok':True}

def _deliver_one(info, message):
    # pywebpush is an optional server dependency, but never silently simulate success.
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info=info, data=json.dumps({
            'title':'LHM Ads AI - Cảnh báo ngân sách','body':message,'url':'/studio'
        },ensure_ascii=False),vapid_private_key=os.environ['LHM_VAPID_PRIVATE_KEY_FILE'],
        vapid_claims={'sub':os.environ['LHM_VAPID_SUBJECT']},ttl=180)
        return 'sent'
    except WebPushException as exc:
        if getattr(getattr(exc,'response',None),'status_code',None) in (404,410):
            return 'gone'
        return 'failed'

async def deliver_to_org(org,message):
    if not push_available():
        return {'sent':0,'reason':'vapid_not_configured'}
    init_push_db()
    with connection() as db:
        rows=[dict(x) for x in db.execute("""SELECT p.endpoint_hash,p.sealed FROM push_subscriptions p
          JOIN users u ON u.id=p.user_id WHERE p.org_id=? AND u.org_id=?
          AND u.disabled=0""",(org,org)).fetchall()]
    sent=0
    for item in rows:
        try:
            info=json.loads(unseal(item['sealed'],'push:'+item['endpoint_hash']))
            status=await asyncio.to_thread(_deliver_one,info,message)
            if status=='sent':sent+=1
            if status=='gone':
                with connection() as db:
                    db.execute('DELETE FROM push_subscriptions WHERE endpoint_hash=?',(item['endpoint_hash'],))
        except Exception:
            continue  # Never leak subscription, token or endpoint in an exception.
    return {'sent':sent}

async def check_budget_after_sample(acc,now):
    """Check provider TODAY only for opted-in, authenticated threshold accounts."""
    init_push_db()
    # May also be invoked by a standalone test or worker without prior monitor init.
    from .monitoring import init_monitor_db
    init_monitor_db()
    with connection() as db:
        rule=db.execute("""SELECT threshold FROM budget_rules WHERE org_id=? AND account_id=?
           AND enabled=1""",(acc['org_id'],acc['id'])).fetchone()
    if not rule:
        return False
    from .providers import fetch_report
    try:
        report=await fetch_report(acc,'today')
        amount=float(report.get('spend'))
        currency=report.get('currency')
        if report.get('source') not in ('google_live','meta_live') or currency!=acc['currency']:
            return False
        if amount<rule['threshold']:
            return False
    except Exception:
        return False
    day=date.fromtimestamp(now).isoformat()
    with connection() as db:
        inserted=db.execute("""INSERT OR IGNORE INTO budget_events
          (org_id,account_id,day,created_at,spend,threshold,currency) VALUES(?,?,?,?,?,?,?)""",
          (acc['org_id'],acc['id'],day,int(now),amount,rule['threshold'],currency))
        if not inserted.rowcount:
            return False
        from .monitoring import _alert
        _alert(db,acc['org_id'],acc['id'],'budget_'+day,
           f'Chi tiêu hôm nay vượt ngưỡng {rule["threshold"]:,.0f} {currency}.',int(now))
    # Public lock-screen text intentionally omits customer names and external Ads IDs.
    message=f'Tài khoản nội bộ #{acc["id"]}: chi phí hôm nay {amount:,.0f} {currency}, vượt ngưỡng {rule["threshold"]:,.0f} {currency}.'
    await deliver_to_org(acc['org_id'],message)
    return True
