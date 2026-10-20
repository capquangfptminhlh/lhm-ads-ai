"""Conservative account-scoped Ads change planning & execution, strictly opt-in.

All provider calls are direct first-party HTTPS; AI and monitoring have no write path.
No endpoint allows unattended auto-execution. No MCP or remotely exposed control.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .app import app, browser_admin, get_account, require
from .db import audit, connection
from .licensing import license_required
from .optimizations import google_access
from .providers import account_token

TARGET = re.compile(r'^\d{5,30}$')
ALLOWED = {
    'google': {'daily_budget', 'manual_cpc'},
    'meta': {'adset_daily_budget', 'adset_bid_cap'},
}
MIN_COOLDOWN = 3600  # 1 hour between accepted edits per ad account
PLAN_TTL = 600       # read-before-write must be rechecked within ten minutes


def init_autopilot_db():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS autopilot_policy (
          org_id TEXT NOT NULL, account_id INTEGER NOT NULL,
          writes_enabled INTEGER NOT NULL DEFAULT 0,
          emergency_stop INTEGER NOT NULL DEFAULT 1,
          max_change_percent INTEGER NOT NULL DEFAULT 10,
          max_changes_per_day INTEGER NOT NULL DEFAULT 2,
          PRIMARY KEY(org_id,account_id));
        CREATE TABLE IF NOT EXISTS autopilot_plans (
          id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL,
          account_id INTEGER NOT NULL, action_type TEXT NOT NULL,
          target_id TEXT NOT NULL, old_value INTEGER NOT NULL,
          new_value INTEGER NOT NULL, currency TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          requested_by INTEGER NOT NULL, reviewed_by INTEGER,
          created_at INTEGER NOT NULL, finished_at INTEGER,
          description TEXT NOT NULL DEFAULT '',
          provider_result TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_autopilot_plans_org ON autopilot_plans(org_id,account_id,status);
        ''')


def policy_of(org, account_id):
    init_autopilot_db()
    with connection() as db:
        row=db.execute('SELECT * FROM autopilot_policy WHERE org_id=? AND account_id=?',
                       (org,account_id)).fetchone()
    return {'writes_enabled':bool(row['writes_enabled']) if row else False,
            'emergency_stop':bool(row['emergency_stop']) if row else True,
            'max_change_percent':row['max_change_percent'] if row else 10,
            'max_changes_per_day':row['max_changes_per_day'] if row else 2}


class PolicyInput(BaseModel):
    writes_enabled: bool = False
    emergency_stop: bool = True
    max_change_percent: int = Field(default=10,ge=1,le=20)
    max_changes_per_day: int = Field(default=2,ge=1,le=5)


@app.get('/api/autopilot/accounts/{account_id}/policy')
def get_policy(account_id:int,ident=Depends(require('admin','operator','reader'))):
    acc=get_account(account_id,ident['org_id'])
    return {'account_id':acc['id'],**policy_of(ident['org_id'],acc['id']),
            'mode':'human_approval_only',
            'notice':'Không có quyền tự động thay đổi khi chưa được admin duyệt từng kế hoạch.'}


@app.put('/api/autopilot/accounts/{account_id}/policy')
def set_policy(account_id:int,body:PolicyInput,ident=Depends(browser_admin)):
    acc=get_account(account_id,ident['org_id'])
    if acc['platform'] not in ALLOWED:raise HTTPException(422,'Chỉ hỗ trợ Google hoặc Meta.')
    if body.writes_enabled and body.emergency_stop:
        raise HTTPException(422,'Để bật quyền chỉnh sửa, phải bỏ Dừng khẩn cấp một cách tường minh.')
    if body.writes_enabled:license_required()
    init_autopilot_db()
    with connection() as db:
        db.execute('''INSERT INTO autopilot_policy(org_id,account_id,writes_enabled,emergency_stop,max_change_percent,max_changes_per_day)
        VALUES (?,?,?,?,?,?) ON CONFLICT(org_id,account_id) DO UPDATE SET writes_enabled=excluded.writes_enabled,
        emergency_stop=excluded.emergency_stop,max_change_percent=excluded.max_change_percent,
        max_changes_per_day=excluded.max_changes_per_day''',
        (ident['org_id'],account_id,int(body.writes_enabled),int(body.emergency_stop),
         body.max_change_percent,body.max_changes_per_day))
        audit(db,ident,'autopilot.policy',f'account={account_id},writes={body.writes_enabled},stop={body.emergency_stop}')
    return get_policy(account_id,ident)


@app.post('/api/autopilot/emergency-stop')
def emergency_stop(ident=Depends(browser_admin)):
    """Fail-closed per tenant. Existing pending plans cannot execute until re-enabled."""
    init_autopilot_db()
    with connection() as db:
        db.execute('UPDATE autopilot_policy SET writes_enabled=0,emergency_stop=1 WHERE org_id=?',
                   (ident['org_id'],))
        audit(db,ident,'autopilot.emergency_stop','All account write permissions stopped')
    return {'ok':True,'mode':'monitor_only'}


class PlanInput(BaseModel):
    account_id: int
    action_type: Literal['daily_budget','manual_cpc','adset_daily_budget','adset_bid_cap']
    target_id: str = Field(min_length=5,max_length=30,pattern=r'^\d{5,30}$')
    new_value: int = Field(ge=1,le=10**15)


def _check_delta(old:int,new:int,max_percent:int):
    if not old or old<=0 or new<=0 or new==old:
        raise HTTPException(422,'Cần giá trị hiện tại dương; giá trị mới phải khác giá trị cũ.')
    # Integer-only boundary (no rounding drift, no floating point).
    if abs(new-old)*100 > old*max_percent:
        raise HTTPException(422,f'Vượt biên độ thay đổi {max_percent}%; giảm mức thay đổi và thử lại.')


def _check_policy(org,aid):
    p=policy_of(org,aid)
    if not p['writes_enabled'] or p['emergency_stop']:
        raise HTTPException(403,'Tài khoản đang ở Monitor Only / Dừng khẩn cấp. Admin phải cho phép chỉnh sửa.')
    return p


def _limit_activity(db,org,account,p,now):
    since=int(datetime.fromtimestamp(now,timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
    count=db.execute('''SELECT COUNT(*) FROM autopilot_plans WHERE org_id=? AND account_id=?
      AND status IN ('executing','completed','accepted_unverified','needs_review') AND finished_at>=?''',
      (org,account,since)).fetchone()[0]
    if count>=p['max_changes_per_day']:
        raise HTTPException(429,'Đã hết hạn mức chỉnh sửa tài khoản trong ngày UTC.')
    recent=db.execute('''SELECT MAX(finished_at) FROM autopilot_plans WHERE org_id=? AND account_id=?
      AND status IN ('executing','completed','accepted_unverified','needs_review')''',
      (org,account)).fetchone()[0]
    if recent is not None and now-recent<MIN_COOLDOWN:
        raise HTTPException(429,'Cần chờ ít nhất 60 phút giữa hai thay đổi trên tài khoản này.')


async def _google_read(acc,kind,target,client):
    customer,version,headers=await google_access(client,acc)
    base=f'https://googleads.googleapis.com/{version}/customers/{customer}'
    if kind=='daily_budget':
        q=('SELECT campaign_budget.id,campaign_budget.amount_micros,campaign_budget.explicitly_shared '
           f'FROM campaign_budget WHERE campaign_budget.id = {target} LIMIT 1')
        obj='campaignBudget';field='amountMicros'
    else:
        q=('SELECT ad_group.id,ad_group.cpc_bid_micros,campaign.bidding_strategy_type '
           f'FROM ad_group WHERE ad_group.id = {target} LIMIT 1')
        obj='adGroup';field='cpcBidMicros'
    r=await client.post(base+'/googleAds:searchStream',headers=headers,json={'query':q})
    if r.status_code!=200:raise HTTPException(502,'Không đọc được giá trị hiện tại Google Ads hoặc quyền API không đủ.')
    try:
        rows=[x[obj] for pg in r.json() for x in pg.get('results',[]) if obj in x]
        if len(rows)!=1 or str(rows[0].get('id'))!=target:
            raise HTTPException(404,'Không tìm thấy mục tiêu trong đúng tài khoản Google Ads.')
        v=rows[0]
        if kind=='daily_budget' and v.get('explicitlyShared') is not False:
            raise HTTPException(422,'Không hỗ trợ sửa ngân sách dùng chung hoặc không xác định được shared budget.')
        if kind=='manual_cpc' and v.get('campaign',{}).get('biddingStrategyType')!='MANUAL_CPC':
            # GAQL may return campaign field on the entry instead of nested adGroup.
            # Checked explicitly below when parsing the original row.
            first=next(x for pg in r.json() for x in pg.get('results',[]) if obj in x)
            if first.get('campaign',{}).get('biddingStrategyType')!='MANUAL_CPC':
                raise HTTPException(422,'Chỉ chỉnh CPC thủ công của ad group dùng MANUAL_CPC; Smart Bidding phải duyệt chiến lược riêng.')
        old=int(v[field])
        if old<=0:raise HTTPException(422,'Không thể sửa khi Google Ads chưa có giá trị gốc.')
        return old,base,headers
    except (ValueError,KeyError,TypeError,StopIteration):
        raise HTTPException(502,'Google Ads trả về dữ liệu mục tiêu không hợp lệ.') from None


async def _meta_read(acc,kind,target,client):
    version=__import__('os').getenv('META_GRAPH_VERSION','v24.0')
    if not re.fullmatch(r'v\d+\.\d+',version):raise HTTPException(503,'Phiên bản Meta API không hợp lệ.')
    base=f'https://graph.facebook.com/{version}'
    headers={'Authorization':'Bearer '+account_token(acc)}
    r=await client.get(f'{base}/{target}',headers=headers,
                       params={'fields':'id,account_id,daily_budget,bid_amount,bid_strategy,status,effective_status'})
    if r.status_code!=200:raise HTTPException(502,'Không thể đọc Meta Ad Set; kiểm tra token và quyền tài khoản.')
    try:
        x=r.json()
        aid=str(acc['external_id']).removeprefix('act_')
        if str(x.get('id'))!=target or str(x.get('account_id','')).removeprefix('act_')!=aid:
            raise HTTPException(403,'Meta Ad Set không thuộc tài khoản đã chọn.')
        if str(x.get('status')) not in ('ACTIVE','PAUSED'):
            raise HTTPException(422,'Trạng thái Meta Ad Set không hỗ trợ chỉnh sửa.')
        if kind=='adset_bid_cap' and x.get('bid_strategy') not in ('LOWEST_COST_WITH_BID_CAP','COST_CAP'):
            raise HTTPException(422,'Chỉ cho phép chỉnh giá thầu khi ad set dùng Bid Cap hoặc Cost Cap.')
        field='daily_budget' if kind=='adset_daily_budget' else 'bid_amount'
        old=int(x.get(field) or 0)
        if old<=0:raise HTTPException(422,'Meta Ad Set không có giá trị gốc có thể chỉnh.')
        return old,base,headers
    except (ValueError,KeyError,TypeError):
        raise HTTPException(502,'Meta trả về giá trị Ad Set không hợp lệ.') from None


async def _snapshot(acc,kind,target,client):
    return await (_google_read(acc,kind,target,client) if acc['platform']=='google' else _meta_read(acc,kind,target,client))


@app.post('/api/autopilot/plans')
async def create_plan(body:PlanInput,ident=Depends(require('admin','operator'))):
    acc=get_account(body.account_id,ident['org_id'])
    if body.action_type not in ALLOWED.get(acc['platform'],set()):
        raise HTTPException(422,'Thao tác không hỗ trợ cho nền tảng này.')
    license_required()
    p=_check_policy(ident['org_id'],acc['id'])
    async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=6),trust_env=False) as c:
        old,_,_=await _snapshot(acc,body.action_type,body.target_id,c)
    _check_delta(old,body.new_value,p['max_change_percent'])
    now=int(time.time())
    with connection() as db:
        _limit_activity(db,ident['org_id'],acc['id'],p,now)
        cur=db.execute('''INSERT INTO autopilot_plans(org_id,account_id,action_type,target_id,old_value,
          new_value,currency,status,requested_by,created_at,description)
          VALUES(?,?,?,?,?,?,?,'pending',?,?,?)''',
          (ident['org_id'],acc['id'],body.action_type,body.target_id,old,body.new_value,
           acc['currency'],ident['id'],now,'Chỉ admin được duyệt; so khớp giá trị hiện tại trước khi ghi.'))
        audit(db,ident,'autopilot.plan',f'plan={cur.lastrowid},account={acc["id"]},type={body.action_type}')
    return {'id':cur.lastrowid,'status':'pending','old_value':old,'new_value':body.new_value,
            'unit':'google_currency_micros' if acc['platform']=='google' else 'meta_api_minor_units',
            'review_before':now+PLAN_TTL,'notice':'Chưa gửi lệnh chỉnh sửa; phải phê duyệt riêng.'}


@app.get('/api/autopilot/plans')
def list_plans(ident=Depends(require('admin','operator','reader'))):
    init_autopilot_db()
    with connection() as db:
        rows=db.execute('''SELECT p.id,p.account_id,a.label as account_label,a.platform,
          p.action_type,p.target_id,p.old_value,p.new_value,p.currency,p.status,
          p.created_at,p.finished_at,p.provider_result
          FROM autopilot_plans p JOIN accounts a ON a.id=p.account_id AND a.org_id=p.org_id
          WHERE p.org_id=? ORDER BY p.id DESC LIMIT 80''',(ident['org_id'],)).fetchall()
        return [dict(row) for row in rows]


async def _apply_google(acc,kind,target,value,base,headers,client):
    if kind=='daily_budget':
        path=base+'/campaignBudgets:mutate'
        resource=base.rsplit('/',1)[-1]
        name=f'customers/{resource}/campaignBudgets/{target}'
        operation={'update':{'resourceName':name,'amountMicros':str(value)},'updateMask':'amount_micros'}
    else:
        path=base+'/adGroups:mutate'
        resource=base.rsplit('/',1)[-1]
        name=f'customers/{resource}/adGroups/{target}'
        operation={'update':{'resourceName':name,'cpcBidMicros':str(value)},'updateMask':'cpc_bid_micros'}
    for dry in (True,False):
        try:
            r=await client.post(path,headers=headers,json={'operations':[operation],
                                 'validateOnly':dry,'partialFailure':False})
        except httpx.HTTPError:
            raise HTTPException(502,'Kết quả Google Ads chưa rõ; KHÔNG gửi lại lệnh khi chưa kiểm tra trạng thái.') from None
        if r.status_code!=200:
            raise HTTPException(403 if dry else 502,
                'Google Ads từ chối validateOnly.' if dry else 'Lệnh Google Ads không được xác nhận; cần kiểm tra thủ công.')
        if not dry:
            try:
                results=r.json()['results']
                if not results or results[0].get('resourceName')!=name:raise ValueError('result')
            except (TypeError,ValueError,KeyError,IndexError):
                raise HTTPException(502,'Không xác nhận được kết quả ghi Google; cần kiểm tra thủ công.') from None
    return True


async def _apply_meta(kind,target,value,base,headers,client):
    field='daily_budget' if kind=='adset_daily_budget' else 'bid_amount'
    try:
        r=await client.post(f'{base}/{target}',headers=headers,data={field:str(value)})
    except httpx.HTTPError:
        raise HTTPException(502,'Lệnh Meta có thể đã thực thi; KHÔNG gửi lại trước khi kiểm tra trạng thái.') from None
    if r.status_code!=200 or r.json().get('success') is not True:
        raise HTTPException(502,'Meta chưa xác nhận cập nhật. Cần kiểm tra thủ công trước khi thử lại.')
    return True


@app.post('/api/autopilot/plans/{plan_id}/approve')
async def approve_plan(plan_id:int,ident=Depends(browser_admin)):
    license_required()
    init_autopilot_db()
    now=int(time.time())
    with connection() as db:
        row=db.execute('''SELECT p.* FROM autopilot_plans p WHERE p.id=? AND p.org_id=?''',
                       (plan_id,ident['org_id'])).fetchone()
        if not row:raise HTTPException(404,'Kế hoạch không tồn tại.')
        if row['status']!='pending':raise HTTPException(409,'Kế hoạch không còn chờ duyệt.')
        if now-row['created_at']>PLAN_TTL:raise HTTPException(409,'Kế hoạch đã quá 10 phút; hãy tạo mới để cập nhật giá trị.')
        acc=get_account(row['account_id'],ident['org_id'])
        p=_check_policy(ident['org_id'],acc['id'])
        _check_delta(row['old_value'],row['new_value'],p['max_change_percent'])
        _limit_activity(db,ident['org_id'],acc['id'],p,now)
        pending_active=db.execute("SELECT 1 FROM autopilot_plans WHERE org_id=? AND account_id=? AND status='executing' AND id<>? LIMIT 1",(ident['org_id'],acc['id'],plan_id)).fetchone()
        if pending_active:raise HTTPException(409,'Có một lệnh khác đang được thực thi trên tài khoản này.')
        updated=db.execute('''UPDATE autopilot_plans SET status='executing',reviewed_by=?,finished_at=?
                             WHERE id=? AND org_id=? AND status='pending' ''',
                           (ident['id'],now,plan_id,ident['org_id']))
        if updated.rowcount!=1:raise HTTPException(409,'Kế hoạch đã được xử lý.')
        audit(db,ident,'autopilot.approve',f'plan={plan_id},account={acc["id"]}')
    state='needs_review'
    detail='Lệnh có thể đã thực thi; cần kiểm tra trạng thái tại nền tảng quảng cáo.'
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30,connect=7),trust_env=False) as c:
            observed,base,headers=await _snapshot(acc,row['action_type'],row['target_id'],c)
            if observed!=row['old_value']:
                state='rejected_stale'
                detail='Giá trị đã thay đổi từ lúc tạo kế hoạch; không gửi lệnh ghi.'
                raise HTTPException(409,detail)
            # Emergency stop / policy may have changed while the API read was in flight.
            _check_policy(ident['org_id'],acc['id'])
            if acc['platform']=='google':
                await _apply_google(acc,row['action_type'],row['target_id'],row['new_value'],base,headers,c)
            else:
                await _apply_meta(row['action_type'],row['target_id'],row['new_value'],base,headers,c)
            state='accepted_unverified'
            detail='API tiếp nhận lệnh; đang cần kiểm tra kết quả sau khi đồng bộ.'
            try:
                current,_,_=await _snapshot(acc,row['action_type'],row['target_id'],c)
                if current==row['new_value']:
                    state='completed'
                    detail='Đã đọc lại đúng giá trị mới từ API quảng cáo.'
            except Exception:
                pass
    except HTTPException as exc:
        if state!='rejected_stale':
            detail=str(exc.detail)[:180]
        raise_exc=exc
    except Exception:
        raise_exc=HTTPException(502,'Không xác định được kết quả; cần kiểm tra tài khoản trước khi thực hiện thao tác khác.')
    else:
        raise_exc=None
    finally:
        with connection() as db:
            db.execute('''UPDATE autopilot_plans SET status=?,provider_result=?,finished_at=?
              WHERE id=? AND org_id=?''',(state,detail,int(time.time()),plan_id,ident['org_id']))
            audit(db,ident,'autopilot.result',f'plan={plan_id},status={state}')
    if raise_exc:raise raise_exc
    return {'ok':state=='completed','status':state,'detail':detail}


@app.post('/api/autopilot/plans/{plan_id}/reject')
def reject_plan(plan_id:int,ident=Depends(browser_admin)):
    init_autopilot_db()
    with connection() as db:
        c=db.execute('''UPDATE autopilot_plans SET status='rejected',reviewed_by=?,finished_at=?
          WHERE id=? AND org_id=? AND status='pending' ''',(ident['id'],int(time.time()),plan_id,ident['org_id']))
        if c.rowcount!=1:raise HTTPException(409,'Kế hoạch không còn chờ duyệt.')
        audit(db,ident,'autopilot.reject',f'plan={plan_id}')
    return {'ok':True}