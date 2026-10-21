"""Local commercial preflight. Never guess live Ads API rights or EXE signing."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import Depends, Request
from .app import app, browser_admin
from .db import connection
from .desktop_onboarding import desktop_only
from .desktop_setup import public_summary
from .licensing import read_license


def readiness_report(org: str) -> dict:
    with connection() as db:
        rows=db.execute("""SELECT platform,COUNT(*) AS total,
             SUM(CASE WHEN token_ciphertext IS NOT NULL THEN 1 ELSE 0 END) AS configured
             FROM accounts WHERE org_id=? AND label NOT LIKE '[REVOKED]%'
             GROUP BY platform""",(org,)).fetchall()
        quick=db.execute('PRAGMA quick_check').fetchone()
    counts={row['platform']:{'accounts':row['total'],'credentials_saved':row['configured']}
            for row in rows}
    oauth=public_summary(org)
    subscription=read_license()
    checks=[
        {'code':'local_storage','status':'ok' if quick and quick[0]=='ok' else 'blocked',
         'detail':'SQLite local integrity check'},
        {'code':'license','status':'ok' if subscription['active'] else 'action_required',
         'detail':'Signed subscription valid for this device'},
        {'code':'oauth_google','status':'configured' if oauth['google']['configured'] else 'action_required',
         'detail':'Google Desktop OAuth App settings only; not Ads API authorization'},
        {'code':'oauth_meta','status':'configured' if oauth['meta']['configured'] else 'action_required',
         'detail':'Meta App settings only; production App Review may be needed'},
        {'code':'live_api','status':'not_verified','detail':'No real provider call was performed'},
        {'code':'authenticode','status':'not_verified','detail':'EXE publisher signature has not been checked'},
        {'code':'secure_backup','status':'available','detail':'Password-encrypted manual backup; offline-assisted restore'},
        {'code':'billing','status':'manual','detail':'Payment and invoicing not automated'},
    ]
    return {'edition':subscription['edition'],
            'license_active':subscription['active'],
            'license_expires_at':subscription.get('expires_at'),
            'provider_account_counts':counts,
            'checks':checks,
            'ready_for_commercial_distribution':False,
            'reason':'Chưa xác minh API quảng cáo thật, chữ ký EXE và chính sách vận hành.',
            'generated_at_utc':datetime.now(timezone.utc).isoformat()}


@app.get('/api/desktop/readiness')
def desktop_readiness(request:Request,ident=Depends(browser_admin)):
    desktop_only(request)
    return readiness_report(ident['org_id'])
