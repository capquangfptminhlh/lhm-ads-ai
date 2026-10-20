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

class GoalInput(BaseModel):
    enabled: bool = False
    objective: Literal['cpa','roas'] = 'cpa'
    target: float = Field(..., gt=0, le=10**12, allow_inf_nan=False)
    min_conversions: int = Field(default=5, ge=3, le=1000)
    min_clicks: int = Field(default=100, ge=20, le=100000)

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

def goal_for(org, account_id):
    init_goals_db()
    with connection() as db:
        x=db.execute("SELECT enabled,objective,target,min_conversions,min_clicks,currency,updated_at FROM ads_goals WHERE org_id=? AND account_id=?",(org,account_id)).fetchone()
        return dict(x) if x else None

@app.get('/api/goals/accounts/{account_id}')
def read_goal(account_id:int,ident=Depends(require('admin','operator','reader'))):
    acc=get_account(account_id,ident['org_id'])
    goal=goal_for(ident['org_id'],acc['id'])
    return {'account_id':acc['id'],'platform':acc['platform'],'currency':acc['currency'],
            'goal':goal,'evaluation_supported':acc['platform']=='google',
            'note':('Google Ads: chỉ tạo đề xuất từ số liệu chuyển đổi đã ghi nhận, không gửi lệnh ghi.' if acc['platform']=='google'
                    else 'Meta Ads chưa chuẩn hóa conversions/value cho mục tiêu này; sẽ không tạo cảnh báo CPA/ROAS.')}

@app.put('/api/goals/accounts/{account_id}')
def save_goal(account_id:int,body:GoalInput,ident=Depends(browser_admin)):
    acc=get_account(account_id,ident['org_id'])
    if acc['platform'] not in ('google','meta'):
        raise HTTPException(422,'Chỉ hỗ trợ mục tiêu trên Google/Meta Ads.')
    # Explicit settings can be saved for Meta for a future, properly normalized adapter,
    # but must not be evaluated until its conversion data can be trusted.
    if body.objective=='roas' and body.target>1000:
        raise HTTPException(422,'Giá trị ROAS mục tiêu không hợp lệ (hệ số tối đa 1000).')
    if not math.isfinite(body.target):
        raise HTTPException(422,'Mục tiêu phải là số hữu hạn.')
    init_goals_db()
    with connection() as db:
        db.execute("""
          INSERT INTO ads_goals(org_id,account_id,enabled,objective,target,min_conversions,min_clicks,currency)
          VALUES(?,?,?,?,?,?,?,?)
          ON CONFLICT(org_id,account_id) DO UPDATE SET
            enabled=excluded.enabled,objective=excluded.objective,target=excluded.target,
            min_conversions=excluded.min_conversions,min_clicks=excluded.min_clicks,
            currency=excluded.currency,updated_at=CURRENT_TIMESTAMP
        """,(ident['org_id'],acc['id'],int(body.enabled),body.objective,body.target,
             body.min_conversions,body.min_clicks,acc['currency']))
        audit(db,ident,'ads.goal.updated',f'account={acc["id"]},objective={body.objective},enabled={body.enabled}')
    return read_goal(account_id,ident)

def evaluate_goals(campaigns,platform,currency,goal):
    """Return advice only when source KPIs and adequate observations are present.

    Conversions/attribution can lag: results are REVIEW signals, not automated bids.
    """
    if platform!='google' or not goal or not goal['enabled'] or goal['currency']!=currency:
        return []
    out=[]
    for c in campaigns:
        if c.get('status')!='ENABLED':
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
                        'message':f'CPA {value:.2f} {currency} cao hơn mục tiêu {target:.2f} (>20%). Xem lại tracking, độ trễ chuyển đổi và chất lượng lead trước khi thay đổi giá thầu.'})
        if goal['objective']=='roas' and value<target*0.8:
            ratio=value/target
            out.append({'campaign_id':str(c['id']), 'code':'roas_below_goal',
                        'level':'high' if ratio<=0.5 else 'review',
                        'message':f'ROAS {value:.2f} thấp hơn mục tiêu {target:.2f} (>20%). Kiểm tra ghi nhận doanh thu, độ trễ và cấu trúc chiến dịch trước khi chỉnh ngân sách.'})
    return out[:40]
