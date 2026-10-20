"""Local-only 15–240-minute Ads API health/performance collector.

Monitoring is intentionally read-only. Google/Meta report metrics are for LAST_7_DAYS,
NOT live campaign metrics; no claim of real-time bid optimization. The user must
opt in to running a background agent at Windows logon.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
import subprocess

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .app import app, browser_admin, require
from .db import connection, audit, init_db
from .licensing import read_license, license_required
from .providers import fetch_report
from .security import validate_secrets

DEFAULT_POLL_MIN = 60


def init_monitor_db():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS monitor_settings (
          org_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
          poll_minutes INTEGER NOT NULL DEFAULT 60,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS monitor_samples (
          id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL,
          account_id INTEGER NOT NULL, observed_at INTEGER NOT NULL,
          source TEXT, period TEXT NOT NULL DEFAULT 'last_7d',
          currency TEXT, spend REAL, impressions INTEGER, clicks INTEGER,
          error_code TEXT);
        CREATE INDEX IF NOT EXISTS idx_monitor_samples_org ON monitor_samples(org_id, observed_at DESC);
        CREATE TABLE IF NOT EXISTS monitor_alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL,
          account_id INTEGER NOT NULL, created_at INTEGER NOT NULL,
          severity TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL,
          resolved_at INTEGER);
        CREATE INDEX IF NOT EXISTS idx_monitor_alerts_org ON monitor_alerts(org_id,created_at DESC);
        ''')


def get_monitor_settings(org):
    init_monitor_db()
    with connection() as db:
        row=db.execute('SELECT enabled,poll_minutes FROM monitor_settings WHERE org_id=?',(org,)).fetchone()
    return {'enabled':bool(row['enabled']) if row else False,
            'poll_minutes':row['poll_minutes'] if row else DEFAULT_POLL_MIN}


class MonitorSettings(BaseModel):
    enabled: bool
    poll_minutes: int=Field(default=DEFAULT_POLL_MIN,ge=15,le=240)


@app.get('/api/monitor')
def monitor_status(ident=Depends(require('admin','operator','reader'))):
    init_monitor_db()
    with connection() as db:
        samples=[dict(x) for x in db.execute('''SELECT s.account_id,a.label,a.platform,s.observed_at,s.period,
           s.source,s.currency,s.spend,s.impressions,s.clicks,s.error_code FROM monitor_samples s
           JOIN accounts a ON a.id=s.account_id WHERE s.org_id=? ORDER BY s.observed_at DESC,s.id DESC LIMIT 50''',
           (ident['org_id'],)).fetchall()]
        alerts=[dict(x) for x in db.execute('''SELECT al.id,al.account_id,a.label,al.created_at,al.code,al.severity,
          al.message,al.resolved_at FROM monitor_alerts al JOIN accounts a ON a.id=al.account_id
          WHERE al.org_id=? ORDER BY al.id DESC LIMIT 30''',(ident['org_id'],)).fetchall()]
    return {'settings':get_monitor_settings(ident['org_id']),
            'subscription':read_license()['active'],
            'samples':samples,'alerts':alerts,
            'note':'Số liệu giám sát là kỳ 7 ngày gần nhất, không phải realtime; chỉ đọc API, không sửa chiến dịch.'}


@app.put('/api/monitor/settings')
def change_monitor(body:MonitorSettings,ident=Depends(browser_admin)):
    if body.enabled:
        license_required()
    init_monitor_db()
    with connection() as db:
        db.execute('''INSERT INTO monitor_settings(org_id,enabled,poll_minutes) VALUES(?,?,?)
          ON CONFLICT(org_id) DO UPDATE SET enabled=excluded.enabled,poll_minutes=excluded.poll_minutes,
          updated_at=CURRENT_TIMESTAMP''',(ident['org_id'],int(body.enabled),body.poll_minutes))
        audit(db,ident,'monitor.settings',f'enabled={body.enabled}; minutes={body.poll_minutes}')
    return get_monitor_settings(ident['org_id'])


def _alert(db,org,account_id,code,message,now):
    # Throttle identical alerts to at most one per 24 hours per account.
    already=db.execute('''SELECT 1 FROM monitor_alerts WHERE org_id=? AND account_id=? AND code=?
      AND created_at>? LIMIT 1''',(org,account_id,code,now-86400)).fetchone()
    if not already:
        db.execute('INSERT INTO monitor_alerts(org_id,account_id,created_at,severity,code,message) VALUES(?,?,?,?,?,?)',
                   (org,account_id,now,'warning',code,message))


async def collect_account(acc, now):
    # Every network call is to an official authorized provider through providers.fetch_report.
    # Do not send account identifiers or provider credentials to OpenRouter here.
    try:
        output=await fetch_report(acc,'last_7d')
        if output.get('source')=='demo':
            return
        values=(acc['org_id'],acc['id'],now,output.get('source'),output.get('currency'),
                float(output.get('spend') or 0),int(output.get('impressions') or 0),int(output.get('clicks') or 0),None)
    except Exception as exc:
        # Provider error details may contain account info; store only safe generic classifications.
        name=type(exc).__name__
        code='provider_error' if name in ('HTTPException','HTTPStatusError') else 'collector_error'
        values=(acc['org_id'],acc['id'],now,None,None,None,None,None,code)
    with connection() as db:
        db.execute('''INSERT INTO monitor_samples(org_id,account_id,observed_at,source,currency,spend,
          impressions,clicks,error_code) VALUES(?,?,?,?,?,?,?,?,?)''',values)
        if values[-1]:
            _alert(db,acc['org_id'],acc['id'],values[-1],
                   'Không thể cập nhật báo cáo API; kiểm tra Internet và quyền tài khoản Ads.',now)
        # Max 2000 rows/tenant to bound storage without deleting audit history.
        db.execute('''DELETE FROM monitor_samples WHERE org_id=? AND id NOT IN
           (SELECT id FROM monitor_samples WHERE org_id=? ORDER BY id DESC LIMIT 2000)''',
           (acc['org_id'],acc['org_id']))


async def collect_once(now=None, org_ids=None):
    """Read-only cycle. Called from the optional background Windows agent."""
    init_monitor_db()
    if not read_license()['active']:
        return {'checked':0,'reason':'subscription_missing_or_expired'}
    ts=int(time.time()) if now is None else int(now)
    selected=sorted(org_ids) if org_ids is not None else None
    filter_clause=(' AND a.org_id IN ('+','.join('?' for _ in selected)+')') if selected else ''
    with connection() as db:
        sql=("SELECT a.* FROM accounts a JOIN monitor_settings s ON s.org_id=a.org_id AND s.enabled=1 "
             "WHERE a.platform IN ('google','meta') AND a.token_ciphertext IS NOT NULL "
             "AND a.label NOT LIKE '[REVOKED]%'"+filter_clause+
             " ORDER BY COALESCE((SELECT MAX(observed_at) FROM monitor_samples ms "
             "WHERE ms.account_id=a.id AND ms.org_id=a.org_id),0) ASC,a.id ASC LIMIT 20")
        accounts=[dict(r) for r in db.execute(sql,tuple(selected or ())).fetchall()]
    for acc in accounts:
        await collect_account(acc,ts)
    return {'checked':len([a for a in accounts if org_ids is None or a['org_id'] in org_ids]),'observed_at':ts}


async def run_background():
    """Run independently of UI; no listener port or inbound network connections."""
    validate_secrets()
    init_db()
    init_monitor_db()
    from .advisor import heartbeat, scan_account
    # Each enabled org can choose its own schedule, initial pass at startup.
    last_run={}
    while True:
        try:
            heartbeat()
            if read_license()['active']:
                now=time.monotonic()
                with connection() as db:
                    rows=db.execute('SELECT org_id,poll_minutes FROM monitor_settings WHERE enabled=1').fetchall()
                due=[x for x in rows if now-last_run.get(x['org_id'],-10**9)>=x['poll_minutes']*60]
                if due:
                    # collect_once limits work to 20 accounts total; subsequent cycles catch new accounts.
                    await collect_once(org_ids={x['org_id'] for x in due})
                    # Daily-only campaign advice, without an Ads write path.
                    with connection() as db:
                        accts=[dict(a) for a in db.execute("""SELECT a.* FROM accounts a
                         JOIN monitor_settings s ON s.org_id=a.org_id AND s.enabled=1
                         WHERE a.platform IN ('google','meta') AND a.token_ciphertext IS NOT NULL
                         AND a.org_id IN (""" + ','.join('?' for _ in due) + ") LIMIT 20",
                         tuple(x['org_id'] for x in due)).fetchall()]
                    for account in accts:
                        await scan_account(account)
                    for row in due:last_run[row['org_id']]=now
        except Exception:
            # Fail closed: monitoring never performs write operations on providers.
            pass
        await asyncio.sleep(30)


@app.post('/api/monitor/agent/enable')
def enable_windows_agent(ident=Depends(browser_admin)):
    """User-initiated opt-in to HKCU Run key; no admin UAC and no VPS."""
    license_required()
    if os.name!='nt' or not getattr(sys,'frozen',False):
        raise HTTPException(422,'Chỉ hỗ trợ kích hoạt tự chạy từ file EXE trên Windows')
    if not get_monitor_settings(ident['org_id'])['enabled']:
        raise HTTPException(409,'Hãy bật giám sát trong Cài đặt trước')
    import winreg
    run_key=r'Software\Microsoft\Windows\CurrentVersion\Run'
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,run_key,0,winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key,'LHMAdsAIMonitor',0,winreg.REG_SZ,f'"{sys.executable}" --agent-only')
    try:
        subprocess.Popen([sys.executable,'--agent-only'],cwd=os.path.dirname(sys.executable),
                         creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS,
                         close_fds=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        raise HTTPException(503,'Đã bật tự chạy khi đăng nhập Windows, nhưng không thể khởi động ngay')
    with connection() as db:
        audit(db,ident,'monitor.autostart','User opted into Windows HKCU Run background monitor')
    return {'ok':True,'start_on_windows_login':True}


@app.post('/api/monitor/agent/disable')
def disable_windows_agent(ident=Depends(browser_admin)):
    if os.name!='nt':
        raise HTTPException(422,'Chỉ hỗ trợ Windows')
    import winreg
    run_key=r'Software\Microsoft\Windows\CurrentVersion\Run'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,run_key,0,winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key,'LHMAdsAIMonitor')
    except FileNotFoundError:
        pass
    with connection() as db:
        db.execute('UPDATE monitor_settings SET enabled=0 WHERE org_id=?',(ident['org_id'],))
        audit(db,ident,'monitor.autostart','Background monitor disabled and Run key removed')
    return {'ok':True}

# Routes for the local read-only campaign adviser.
from . import advisor  # noqa: E402,F401
