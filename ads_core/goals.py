"""Per-account advertising objectives, evaluated locally from first-party metrics.

No automatic provider writes and no LLM input. Google conversion metrics currently
support CPA/ROAS checks; Meta campaign conversion data is not yet normalized.
"""
from __future__ import annotations

import math
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from .app import app, browser_admin, get_account, require
from .db import connection, audit

# An account must select ONE Meta action type; never blend lead and purchase.
META_LEAD_ACTIONS = frozenset(('lead','offsite_conversion.fb_pixel_lead'))
META_PURCHASE_ACTIONS = frozenset(('purchase','offsite_conversion.fb_pixel_purchase','omni_purchase'))
META_ACTIONS = META_LEAD_ACTIONS | META_PURCHASE_ACTIONS

class GoalInput(BaseModel):
    enabled: bool = False
    objective: Literal['cpa','roas'] = 'cpa'
    target: float = Field(..., gt=0, le=10**12, allow_inf_nan=False)
    min_conversions: int = Field(default=5, ge=3, le=1000)
    min_clicks: int = Field(default=100, ge=20, le=100000)
    meta_action_type: Literal['lead','offsite_conversion.fb_pixel_lead','purchase','offsite_conversion.fb_pixel_purchase','omni_purchase'] | None = None

def init_goals_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS ads_goals (
            org_id TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            objective TEXT NOT NULL CHECK(objective IN ('cpa','roas')),
            target REAL NOT NULL CHECK(target>0),
            min_conversions INTEGER NOT NULL DEFAULT 5,
            min_clicks INTEGER NOT NULL DEFAULT 100,
            currency TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(org_id,account_id)
        );
        """)
        cols={x['name'] for x in db.execute('PRAGMA table_info(ads_goals)')}
        if 'meta_action_type' not in cols:
            db.execute('ALTER TABLE ads_goals ADD COLUMN meta_action_type TEXT')

def goal_for(org, account_id):
    init_goals_db()
    with connection() as db:
        x=db.execute("SELECT enabled,objective,target,min_conversions,min_clicks,currency,meta_action_type,updated_at FROM ads_goals WHERE org_id=? AND account_id=?",(org,account_id)).fetchone()
        return dict(x) if x else None

@app.get('/api/goals/accounts/{account_id}')
def read_goal(account_id:int,ident=Depends(require('admin','operator','reader'))):
    acc=get_account(account_id,ident['org_id'])
    goal=goal_for(ident['org_id'],acc['id'])
    return {'account_id':acc['id'],'platform':acc['platform'],'currency':acc['currency'],
            'goal':goal,'evaluation_supported':acc['platform']=='google' or (
                acc['platform']=='meta' and bool(goal and goal['meta_action_type'])),
            'meta_supported_actions':sorted(META_ACTIONS) if acc['platform']=='meta' else [],
            'note':('Google Ads: đánh giá chuyển đổi đã ghi nhận, không tự gửi lệnh ghi.' if acc['platform']=='google'
                    else 'Meta: chỉ đọc sự kiện đã chọn, attribution 7d_click. Không có action/value hợp lệ thì không tính CPA/ROAS.')}

@app.put('/api/goals/accounts/{account_id}')
def save_goal(account_id:int,body:GoalInput,ident=Depends(browser_admin)):
    acc=get_account(account_id,ident['org_id'])
    if acc['platform'] not in ('google','meta'):
        raise HTTPException(422,'Chỉ hỗ trợ mục tiêu trên Google/Meta Ads.')
    if acc['platform']=='meta' and body.enabled:
        if body.meta_action_type not in META_ACTIONS:
            raise HTTPException(422,'Chọn đúng một loại chuyển đổi Meta trước khi bật mục tiêu.')
        if body.objective=='roas' and body.meta_action_type not in META_PURCHASE_ACTIONS:
            raise HTTPException(422,'ROAS Meta cần sự kiện Purchase có giá trị doanh thu.')
    if acc['platform']=='google' and body.meta_action_type is not None:
        raise HTTPException(422,'Google không dùng loại sự kiện Meta.')
    # Explicit settings can be saved for Meta for a future, properly normalized adapter,
    # but must not be evaluated until its conversion data can be trusted.
    if body.objective=='roas' and body.target>1000:
        raise HTTPException(422,'Giá trị ROAS mục tiêu không hợp lệ (hệ số tối đa 1000).')
    if not math.isfinite(body.target):
        raise HTTPException(422,'Mục tiêu phải là số hữu hạn.')
    init_goals_db()
    with connection() as db:
        db.execute("""
          INSERT INTO ads_goals(org_id,account_id,enabled,objective,target,min_conversions,min_clicks,currency,meta_action_type)
          VALUES(?,?,?,?,?,?,?,?,?)
          ON CONFLICT(org_id,account_id) DO UPDATE SET
            enabled=excluded.enabled,objective=excluded.objective,target=excluded.target,
            min_conversions=excluded.min_conversions,min_clicks=excluded.min_clicks,
            currency=excluded.currency,meta_action_type=excluded.meta_action_type,updated_at=CURRENT_TIMESTAMP
        """,(ident['org_id'],acc['id'],int(body.enabled),body.objective,body.target,
             body.min_conversions,body.min_clicks,acc['currency'],body.meta_action_type if acc['platform']=='meta' else None))
        audit(db,ident,'ads.goal.updated',f'account={acc["id"]},objective={body.objective},enabled={body.enabled}')
    return read_goal(account_id,ident)

def evaluate_goals(campaigns,platform,currency,goal):
    """Return advice only when source KPIs and adequate observations are present.

    Conversions/attribution can lag: results are REVIEW signals, not automated bids.
    """
    if platform not in ('google','meta') or not goal or not goal['enabled'] or goal['currency']!=currency:
        return []
    out=[]
    for c in campaigns:
        if c.get('status')!=('ENABLED' if platform=='google' else 'ACTIVE'):
            continue
        if platform=='meta':
            if (c.get('effective_status') not in (None,'ACTIVE') or
                not goal.get('meta_action_type') or
                c.get('conversion_action_type')!=goal['meta_action_type'] or
                c.get('conversion_source')!='meta_actions_7d_click'):
                continue
        clicks=c.get('clicks')
        conversions=c.get('conversions')
        if clicks is None or conversions is None:
            continue
        try:
            if int(clicks)<goal['min_clicks'] or float(conversions)<goal['min_conversions']:
                continue
            metric=c.get('cpa') if goal['objective']=='cpa' else c.get('roas')
            value=float(metric)
            target=float(goal['target'])
        except (TypeError,ValueError,OverflowError):
            continue
        if not math.isfinite(value) or value<0:
            continue
        if goal['objective']=='cpa' and value>target*1.2:
            ratio=value/target
            out.append({'campaign_id':str(c['id']), 'code':'cpa_above_goal',
                        'level':'high' if ratio>=1.5 else 'review',
                        'message':f'CPA {value:.2f} {currency} cao hơn mục tiêu {target:.2f} (>20%). Xem lại tracking, cửa sổ quy đổi, độ trễ chuyển đổi và chất lượng lead trước khi thay đổi giá thầu.'})
        if goal['objective']=='roas' and value<target*0.8:
            ratio=value/target
            out.append({'campaign_id':str(c['id']), 'code':'roas_below_goal',
                        'level':'high' if ratio<=0.5 else 'review',
                        'message':f'ROAS {value:.2f} thấp hơn mục tiêu {target:.2f} (>20%). Kiểm tra ghi nhận doanh thu, độ trễ và cấu trúc chiến dịch trước khi chỉnh ngân sách.'})
    return out[:40]
