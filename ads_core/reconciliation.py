"""Read-only reconciliation of Google/Meta edits previously approved by an admin.

This module NEVER calls a provider write endpoint. A response that differs from the
requested value is not proof that reverting or retrying a mutation is safe.
"""
from __future__ import annotations

import time

import httpx
from fastapi import Depends, HTTPException

from .app import app, browser_admin, get_account
from .db import audit, connection
from . import autopilot as ap

RECHECK_SECONDS = 15 * 60
MAX_AUTO_ATTEMPTS = 12
VERIFYABLE = ('accepted_unverified', 'needs_review')


def init_reconciliation_db():
    ap.init_autopilot_db()
    with connection() as db:
        existing = {row['name'] for row in db.execute('PRAGMA table_info(autopilot_plans)')}
        for name, sqltype in (
            ('last_verified_at', 'INTEGER'),
            ('verify_attempts', 'INTEGER NOT NULL DEFAULT 0'),
            ('last_observed_value', 'INTEGER'),
            ('last_verify_outcome', "TEXT NOT NULL DEFAULT 'not_checked'"),
        ):
            if name not in existing:
                db.execute(f'ALTER TABLE autopilot_plans ADD COLUMN {name} {sqltype}')


def _get_plan(plan_id, org):
    with connection() as db:
        plan = db.execute(
            "SELECT * FROM autopilot_plans WHERE id=? AND org_id=?",
            (plan_id, org),
        ).fetchone()
    if plan is None:
        raise HTTPException(404, 'Kế hoạch không tồn tại trong đơn vị này.')
    return dict(plan)


async def verify_plan(plan_id: int, org: str):
    """One provider GET/search only; never retries the original mutation."""
    init_reconciliation_db()
    plan = _get_plan(plan_id, org)
    if plan['status'] not in VERIFYABLE:
        raise HTTPException(409, 'Chỉ xác minh các lệnh đã gửi nhưng chưa xác nhận kết quả.')

    # Cross-tenant scope enforced a second time by get_account().
    account = get_account(plan['account_id'], org)
    if account['platform'] not in ('google', 'meta'):
        raise HTTPException(422, 'Chỉ đối soát lệnh Google hoặc Meta.')

    observed = None
    outcome = 'api_unavailable'
    status = plan['status']
    message = 'Chưa đọc được giá trị từ API. Không có lệnh ghi nào được gửi lại.'
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(22, connect=6), trust_env=False) as client:
            observed, _, _ = await ap._snapshot(
                account, plan['action_type'], plan['target_id'], client)
        if observed == plan['new_value']:
            status = 'completed'
            outcome = 'verified_new'
            message = 'Đã đọc lại đúng giá trị mới từ API quảng cáo.'
        elif observed == plan['old_value']:
            outcome = 'still_old'
            message = 'API vẫn trả giá trị cũ. Không tự thử lại lệnh; cần theo dõi hoặc đối chiếu thủ công.'
        else:
            status = 'needs_review'
            outcome = 'unexpected_value'
            message = 'Giá trị API khác cả trước và sau; cần kiểm tra thủ công. Không tự rollback.'
    except Exception:
        # Never persist provider response body, token, URL, or exception text.
        pass

    now = int(time.time())
    with connection() as db:
        changed = db.execute(
            """UPDATE autopilot_plans SET status=?,provider_result=?,
               last_verified_at=?,verify_attempts=verify_attempts+1,
               last_observed_value=?,last_verify_outcome=?
               WHERE id=? AND org_id=? AND status IN ('accepted_unverified','needs_review')""",
            (status, message, now, observed, outcome, plan_id, org),
        )
        if changed.rowcount != 1:
            raise HTTPException(409, 'Trạng thái kế hoạch vừa thay đổi. Vui lòng làm mới.')
        audit(db, {'org_id':org,'id':None}, 'autopilot.verify',
              f'plan={plan_id},status={status},outcome={outcome}')
    return {'id':plan_id,'status':status,'outcome':outcome,'verified_value':observed,
            'checked_at':now,'detail':message,'read_only':True}


@app.post('/api/autopilot/plans/{plan_id}/verify')
async def manual_verify(plan_id: int, ident=Depends(browser_admin)):
    """Admin explicitly asks to check provider state; CSRF required by middleware."""
    return await verify_plan(plan_id, ident['org_id'])


async def reconcile_due(org_ids, now=None):
    """Bounded background pass; only tenants with opted-in monitoring are scanned.

    Called by local Windows agent. Does not perform Ads writes or use a cloud VPS.
    """
    selected=sorted(set(org_ids or []))
    if not selected:
        return {'checked':0}
    init_reconciliation_db()
    stamp=int(time.time()) if now is None else int(now)
    placeholders=','.join('?' for _ in selected)
    with connection() as db:
        rows=db.execute(
            """SELECT p.id,p.org_id FROM autopilot_plans p
               JOIN monitor_settings m ON m.org_id=p.org_id AND m.enabled=1
               WHERE p.org_id IN (""" + placeholders + """)
                 AND p.status IN ('accepted_unverified','needs_review')
                 AND p.verify_attempts < ?
                 AND (p.last_verified_at IS NULL OR p.last_verified_at <= ?)
               ORDER BY COALESCE(p.last_verified_at,0),p.id LIMIT 10""",
            (*selected,MAX_AUTO_ATTEMPTS,stamp-RECHECK_SECONDS),
        ).fetchall()
    completed=0
    for row in rows:
        try:
            await verify_plan(row['id'],row['org_id'])
        except Exception:
            # Read-only checks must never break the report collector.
            continue
        completed+=1
    return {'checked':completed}
