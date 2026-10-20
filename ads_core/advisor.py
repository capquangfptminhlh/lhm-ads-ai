"""Background, read-only campaign optimization findings for locally hosted LHM Ads AI.

This is a deterministic alert engine; it is not an LLM nor a remote Ads writer.
Provider data is requested directly from official APIs, and all findings remain on
this Windows installation. Each account is scanned at most once per UTC day by the
background agent, with retries no sooner than one hour after provider failures.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .app import app, browser_admin, get_account, require
from .db import audit, connection
from .licensing import license_required
from .optimizations import list_live_campaigns, rule_suggestions
from .goals import goal_for, evaluate_goals

DAY = 86400
RETRY = 3600
MAX_FINDINGS = 40


def init_advisor_db():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS advisor_scan_runs (
          org_id TEXT NOT NULL, account_id INTEGER NOT NULL,
          last_attempt_at INTEGER NOT NULL DEFAULT 0,
          last_success_at INTEGER NOT NULL DEFAULT 0,
          error_code TEXT NOT NULL DEFAULT '',
          PRIMARY KEY(org_id, account_id));
        CREATE TABLE IF NOT EXISTS advisor_findings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          org_id TEXT NOT NULL, account_id INTEGER NOT NULL,
          campaign_id TEXT NOT NULL, rule_code TEXT NOT NULL,
          severity TEXT NOT NULL, message TEXT NOT NULL,
          first_seen_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL,
          acknowledged_at INTEGER, acknowledged_by INTEGER,
          UNIQUE(org_id, account_id, campaign_id, rule_code));
        CREATE INDEX IF NOT EXISTS idx_advisor_findings_org
          ON advisor_findings(org_id, acknowledged_at, last_seen_at DESC);
        CREATE TABLE IF NOT EXISTS advisor_agent_heartbeat (
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          last_seen_at INTEGER NOT NULL,
          mode TEXT NOT NULL DEFAULT 'monitor_only');
        ''')
        existing={r['name'] for r in db.execute('PRAGMA table_info(advisor_findings)')}
        if 'resolved_at' not in existing:
            db.execute('ALTER TABLE advisor_findings ADD COLUMN resolved_at INTEGER')


def heartbeat(now=None):
    """Used only by the local Windows background process, never a remote monitor."""
    now = int(time.time()) if now is None else int(now)
    init_advisor_db()
    with connection() as db:
        db.execute('''INSERT INTO advisor_agent_heartbeat(singleton,last_seen_at,mode)
                      VALUES(1,?,'monitor_only') ON CONFLICT(singleton)
                      DO UPDATE SET last_seen_at=excluded.last_seen_at''', (now,))


def agent_health(now=None):
    init_advisor_db()
    now = int(time.time()) if now is None else int(now)
    with connection() as db:
        row = db.execute('SELECT last_seen_at FROM advisor_agent_heartbeat WHERE singleton=1').fetchone()
    last = row['last_seen_at'] if row else None
    return {'last_seen_at':last, 'running':bool(last and 0 <= now-last <= 120),
            'mode':'monitor_only', 'requires_windows_running':True}


async def scan_account(acc, *, now=None, min_interval=DAY):
    """Rate limited campaign scan with a durable claim across multiple processes.

    Never invokes any ad-mutating API. Claims before network I/O so duplicate
    scheduler processes cannot run provider requests in parallel.
    """
    if acc['platform'] not in ('google', 'meta') or not acc.get('token_ciphertext'):
        raise HTTPException(422,'Chỉ quét tài khoản Google/Meta đã kết nối API thật.')
    now = int(time.time()) if now is None else int(now)
    init_advisor_db()
    with connection() as db:
        db.execute('INSERT OR IGNORE INTO advisor_scan_runs(org_id,account_id) VALUES (?,?)',
                   (acc['org_id'],acc['id']))
        row = db.execute('SELECT * FROM advisor_scan_runs WHERE org_id=? AND account_id=?',
                         (acc['org_id'],acc['id'])).fetchone()
        if row['last_success_at'] and now-row['last_success_at'] < min_interval:
            return {'scanned':False,'reason':'already_checked','recommendations':0}
        if row['last_attempt_at'] and now-row['last_attempt_at'] < RETRY:
            return {'scanned':False,'reason':'retry_cooldown','recommendations':0}
        claimed = db.execute('''UPDATE advisor_scan_runs SET last_attempt_at=?,error_code=''
                   WHERE org_id=? AND account_id=? AND last_attempt_at=?''',
                   (now,acc['org_id'],acc['id'],row['last_attempt_at']))
        if claimed.rowcount != 1:
            return {'scanned':False,'reason':'concurrent_scan','recommendations':0}
    try:
        campaigns = await list_live_campaigns(acc)
        findings = rule_suggestions(campaigns,acc['platform'],acc['currency'])
        objective = goal_for(acc['org_id'],acc['id'])
        findings += evaluate_goals(campaigns,acc['platform'],acc['currency'],objective)
        suggestions = findings[:MAX_FINDINGS]
    except Exception:
        # Do not store upstream response bodies or provider token-bearing error text.
        with connection() as db:
            db.execute('''UPDATE advisor_scan_runs SET error_code='provider_unavailable'
                          WHERE org_id=? AND account_id=?''',(acc['org_id'],acc['id']))
        return {'scanned':False,'reason':'provider_unavailable','recommendations':0}
    with connection() as db:
        for r in suggestions:
            if r.get('code') not in ('low_ctr','no_reported_conversions','cpa_above_goal','roas_below_goal'):
                continue
            db.execute('''INSERT INTO advisor_findings(org_id,account_id,campaign_id,rule_code,
                          severity,message,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(org_id,account_id,campaign_id,rule_code) DO UPDATE SET
                      last_seen_at=excluded.last_seen_at, message=excluded.message,
                      severity=excluded.severity,
                      acknowledged_at=CASE WHEN advisor_findings.resolved_at IS NOT NULL
                                           THEN NULL ELSE advisor_findings.acknowledged_at END,
                      acknowledged_by=CASE WHEN advisor_findings.resolved_at IS NOT NULL
                                           THEN NULL ELSE advisor_findings.acknowledged_by END,
                      resolved_at=NULL''',
                       (acc['org_id'],acc['id'],str(r['campaign_id']),r['code'],
                        'high' if r.get('level')=='high' else 'review',str(r['message'])[:450],now,now))
        # Resolve a vanished issue only when its campaign is in this successful
        # provider response. A truncated API page must NOT clear unseen campaigns.
        if len(findings) <= MAX_FINDINGS:
            observed_ids={str(c.get('id')) for c in campaigns}
            active={(str(x['campaign_id']),x['code']) for x in suggestions}
            current=db.execute('''SELECT id,campaign_id,rule_code FROM advisor_findings
                WHERE org_id=? AND account_id=? AND resolved_at IS NULL''',
                (acc['org_id'],acc['id'])).fetchall()
            for previous in current:
                if previous['campaign_id'] in observed_ids and (previous['campaign_id'],previous['rule_code']) not in active:
                    db.execute('UPDATE advisor_findings SET resolved_at=? WHERE id=? AND org_id=?',
                               (now,previous['id'],acc['org_id']))
        db.execute('''UPDATE advisor_scan_runs SET last_success_at=?,error_code=''
                      WHERE org_id=? AND account_id=?''',(now,acc['org_id'],acc['id']))
    return {'scanned':True,'reason':'ok','recommendations':len(suggestions),
            'note':'Phát hiện bằng quy tắc đọc dữ liệu, KHÔNG thay đổi giá thầu hoặc ngân sách.'}


@app.get('/api/advisor/status')
def advisor_status(ident=Depends(require('admin','operator','reader'))):
    init_advisor_db()
    with connection() as db:
        rows=db.execute('''SELECT a.id,a.account_id,ac.label AS account_label,ac.platform,
            a.campaign_id,a.rule_code,a.severity,a.message,a.first_seen_at,a.last_seen_at,
            a.acknowledged_at,a.resolved_at FROM advisor_findings a
            JOIN accounts ac ON ac.id=a.account_id AND ac.org_id=a.org_id
            WHERE a.org_id=? ORDER BY a.resolved_at IS NOT NULL,
            a.acknowledged_at IS NOT NULL,a.last_seen_at DESC, a.id DESC LIMIT 80''',(ident['org_id'],)).fetchall()
        scans=db.execute('''SELECT account_id,last_success_at,last_attempt_at,error_code
                            FROM advisor_scan_runs WHERE org_id=? ORDER BY last_attempt_at DESC LIMIT 80''',
                         (ident['org_id'],)).fetchall()
    return {'agent':agent_health(), 'findings':[dict(r) for r in rows],
            'scans':[dict(r) for r in scans],
            'note':'Tự quét tối đa 1 lần/ngày/tài khoản trên máy Windows còn bật; chỉ tạo cảnh báo, không tự sửa quảng cáo.'}


@app.post('/api/advisor/accounts/{account_id}/scan')
async def scan_from_ui(account_id:int,ident=Depends(browser_admin)):
    license_required()
    acc=get_account(account_id,ident['org_id'])
    result=await scan_account(acc,min_interval=RETRY)
    with connection() as db:
        audit(db,ident,'advisor.scan',f'account={account_id},scanned={result["scanned"]}')
    return result


@app.post('/api/advisor/findings/{finding_id}/acknowledge')
def acknowledge(finding_id:int,ident=Depends(browser_admin)):
    init_advisor_db()
    with connection() as db:
        c=db.execute('''UPDATE advisor_findings SET acknowledged_at=?,acknowledged_by=?
                        WHERE id=? AND org_id=? AND acknowledged_at IS NULL''',
                     (int(time.time()),ident['id'],finding_id,ident['org_id']))
        if c.rowcount!=1:
            raise HTTPException(404,'Cảnh báo không tồn tại hoặc đã được xử lý.')
        audit(db,ident,'advisor.acknowledge',f'finding={finding_id}')
    return {'ok':True}