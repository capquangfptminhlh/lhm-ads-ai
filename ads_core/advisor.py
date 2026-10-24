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

from .app import app, browser_admin, get_account, notify_telegram, require
from .db import audit, connection
from .licensing import license_required
from .optimizations import list_live_campaigns, rule_suggestions
from .goals import goal_for, evaluate_goals
from . import optimization_playbook
import json as _json

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
        CREATE TABLE IF NOT EXISTS advisor_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          org_id TEXT NOT NULL, account_id INTEGER NOT NULL,
          taken_at INTEGER NOT NULL, campaigns_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_advisor_snapshots_account
          ON advisor_snapshots(org_id, account_id, taken_at DESC);
        CREATE TABLE IF NOT EXISTS advisor_outcomes (
          finding_id INTEGER PRIMARY KEY,
          verdict TEXT NOT NULL, checked_at INTEGER NOT NULL);
        ''')
        existing={r['name'] for r in db.execute('PRAGMA table_info(advisor_findings)')}
        if 'resolved_at' not in existing:
            db.execute('ALTER TABLE advisor_findings ADD COLUMN resolved_at INTEGER')
        if 'detail' not in existing:
            db.execute('ALTER TABLE advisor_findings ADD COLUMN detail TEXT')
        # After the resolved_at ALTER above: the per-scan lookups filter
        # findings by (org_id, account_id, resolved_at IS NULL), which the
        # org index (acknowledged_at second) cannot serve.
        db.execute('''CREATE INDEX IF NOT EXISTS idx_advisor_findings_account
                      ON advisor_findings(org_id, account_id, resolved_at)''')


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


# Stored advisor_findings.severity values are 'high' (scan_account stores
# both playbook level 'critical' and goal level 'high' under 'high'),
# 'review' and 'opportunity'. The digest presents the top bucket under its
# playbook name 'critical'; any unexpected stored value is counted under
# its own name so nothing is silently dropped.
_DIGEST_LEVEL_ALIASES = {'high': 'critical', 'critical': 'critical',
                         'review': 'review', 'opportunity': 'opportunity'}


def findings_digest(org, account_id, *, new_codes=None, max_new_titles=3):
    """Compact per-account summary of ACTIVE advisor findings.

    Read-only over the existing advisor_findings table (no new store, no
    new network destination, no campaign names or account labels — rule
    codes and counts only). Returns::

        {'account_id': int,
         'active_counts': {'critical': n, 'review': n, 'opportunity': n},
         'active_total': n,
         'new': [{'code': str, 'title': str | None}, ...]}

    'Active' means resolved_at IS NULL (acknowledged findings still count
    until they resolve). 'new' lists up to ``max_new_titles`` entries: the
    codes passed in ``new_codes`` when given (the genuinely-new codes of a
    scan, in scan order), otherwise the most recently first-seen active
    findings. Titles come from the shipped playbook catalog
    (optimization_playbook.PLAYBOOK); codes outside the catalog (legacy
    rule codes) get title None.
    """
    init_advisor_db()
    titles = {entry['code']: entry.get('title')
              for entry in optimization_playbook.PLAYBOOK}
    with connection() as db:
        rows = db.execute('''SELECT severity,COUNT(*) AS n FROM advisor_findings
            WHERE org_id=? AND account_id=? AND resolved_at IS NULL
            GROUP BY severity''', (org, account_id)).fetchall()
        if new_codes is None:
            codes = [r['rule_code'] for r in db.execute(
                '''SELECT rule_code FROM advisor_findings
                   WHERE org_id=? AND account_id=? AND resolved_at IS NULL
                   ORDER BY first_seen_at DESC, id DESC''',
                (org, account_id)).fetchall()]
            # A code can repeat across campaigns; the digest lists it once.
            codes = list(dict.fromkeys(codes))
        else:
            codes = list(dict.fromkeys(str(c) for c in new_codes))
    counts = {'critical': 0, 'review': 0, 'opportunity': 0}
    total = 0
    for row in rows:
        key = _DIGEST_LEVEL_ALIASES.get(row['severity'], row['severity'])
        counts[key] = counts.get(key, 0) + row['n']
        total += row['n']
    return {'account_id': account_id,
            'active_counts': counts,
            'active_total': total,
            'new': [{'code': code, 'title': titles.get(code)}
                    for code in codes[:max(0, max_new_titles)]]}


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
        # LHM Optimization Loop (docs/OPTIMIZATION_SKILL.md): per-account
        # baselines come from this install's own earlier scan snapshots —
        # never from other customers or any central service.
        baselines = {}
        with connection() as db:
            history = db.execute('''SELECT taken_at,campaigns_json FROM advisor_snapshots
                WHERE org_id=? AND account_id=? ORDER BY taken_at DESC LIMIT 12''',
                (acc['org_id'],acc['id'])).fetchall()
        flat_history = []
        for snap in history:
            for c in _json.loads(snap['campaigns_json']):
                flat_history.append({**c, 'period': str(snap['taken_at'])})
        if flat_history:
            baselines = optimization_playbook.compute_baselines(flat_history)
        playbook_findings = optimization_playbook.evaluate_campaigns(
            campaigns, acc['platform'], acc['currency'], goal=objective,
            baselines=baselines)
        playbook_findings += optimization_playbook.evaluate_account(
            campaigns, acc['platform'], acc['currency'], goal=objective)
        # The playbook's rules are richer (steps + guardrails) than the two
        # older sources: when the playbook speaks on the same signal for a
        # campaign, drop the older duplicate (goal CPA/ROAS codes, the
        # zero-conversion code, and the identical low_ctr code).
        covered = {str(f['campaign_id']) for f in playbook_findings
                   if f['code'] in ('cpa_above_target','roas_below_target')}
        covered_spend = {str(f['campaign_id']) for f in playbook_findings
                         if f['code'] == 'spend_no_conversions'}
        findings = [f for f in findings
                    if not (f['code'] in ('cpa_above_goal','roas_below_goal')
                            and str(f['campaign_id']) in covered)
                    and not (f['code'] == 'no_reported_conversions'
                             and str(f['campaign_id']) in covered_spend)
                    and not (f['code'] == 'low_ctr'
                             and any(p['code'] == 'low_ctr'
                                     and str(p['campaign_id']) == str(f['campaign_id'])
                                     for p in playbook_findings))]
        findings += playbook_findings
        suggestions = findings[:MAX_FINDINGS]
    except Exception:
        # Do not store upstream response bodies or provider token-bearing error text.
        with connection() as db:
            db.execute('''UPDATE advisor_scan_runs SET error_code='provider_unavailable'
                          WHERE org_id=? AND account_id=?''',(acc['org_id'],acc['id']))
        return {'scanned':False,'reason':'provider_unavailable','recommendations':0}
    new_codes=[]
    with connection() as db:
        open_keys={(str(x['campaign_id']),x['rule_code']) for x in db.execute(
            '''SELECT campaign_id,rule_code FROM advisor_findings
               WHERE org_id=? AND account_id=? AND resolved_at IS NULL''',
            (acc['org_id'],acc['id'])).fetchall()}
        allowed_codes = {'low_ctr','no_reported_conversions','cpa_above_goal','roas_below_goal'}
        allowed_codes |= {entry['code'] for entry in optimization_playbook.PLAYBOOK}
        for r in suggestions:
            if r.get('code') not in allowed_codes:
                continue
            if (str(r['campaign_id']),r['code']) not in open_keys and r['code'] not in new_codes:
                new_codes.append(r['code'])
            severity = {'critical':'high','high':'high','review':'review',
                        'opportunity':'opportunity'}.get(r.get('level'),'review')
            detail = None
            if r.get('playbook'):
                detail = _json.dumps({'playbook': r['playbook'],
                                      'suppressed': r.get('suppressed') or []},
                                     ensure_ascii=False)[:4000]
            db.execute('''INSERT INTO advisor_findings(org_id,account_id,campaign_id,rule_code,
                          severity,message,detail,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(org_id,account_id,campaign_id,rule_code) DO UPDATE SET
                      last_seen_at=excluded.last_seen_at, message=excluded.message,
                      severity=excluded.severity, detail=excluded.detail,
                      acknowledged_at=CASE WHEN advisor_findings.resolved_at IS NOT NULL
                                           THEN NULL ELSE advisor_findings.acknowledged_at END,
                      acknowledged_by=CASE WHEN advisor_findings.resolved_at IS NOT NULL
                                           THEN NULL ELSE advisor_findings.acknowledged_by END,
                      resolved_at=NULL''',
                       (acc['org_id'],acc['id'],str(r['campaign_id']),r['code'],
                        severity,str(r['message'])[:450],detail,now,now))
        # Resolve a vanished issue only when its campaign is in this successful
        # provider response. A truncated API page must NOT clear unseen campaigns.
        if len(findings) < MAX_FINDINGS:
            observed_ids={str(c.get('id')) for c in campaigns}
            active={(str(x['campaign_id']),x['code']) for x in suggestions}
            current=db.execute('''SELECT id,campaign_id,rule_code FROM advisor_findings
                WHERE org_id=? AND account_id=? AND resolved_at IS NULL''',
                (acc['org_id'],acc['id'])).fetchall()
            for previous in current:
                if previous['campaign_id'] in observed_ids and (previous['campaign_id'],previous['rule_code']) not in active:
                    db.execute('UPDATE advisor_findings SET resolved_at=? WHERE id=? AND org_id=?',
                               (now,previous['id'],acc['org_id']))
                elif previous['campaign_id']=='ACCOUNT' and ('ACCOUNT',previous['rule_code']) not in active:
                    # Account-level findings are recomputed from the full
                    # campaign list each scan, so absence means resolved.
                    db.execute('UPDATE advisor_findings SET resolved_at=? WHERE id=? AND org_id=?',
                               (now,previous['id'],acc['org_id']))
        # Snapshot this scan for future baselines; keep the newest 12.
        db.execute('INSERT INTO advisor_snapshots(org_id,account_id,taken_at,campaigns_json) VALUES(?,?,?,?)',
                   (acc['org_id'],acc['id'],now,_json.dumps(campaigns,ensure_ascii=False)[:200000]))
        db.execute('''DELETE FROM advisor_snapshots WHERE org_id=? AND account_id=? AND id NOT IN
                      (SELECT id FROM advisor_snapshots WHERE org_id=? AND account_id=?
                       ORDER BY taken_at DESC LIMIT 12)''',
                   (acc['org_id'],acc['id'],acc['org_id'],acc['id']))
        # Outcome verification loop: for playbook findings first seen at
        # least 7 days ago and not yet verdicted, compare the campaign's
        # metrics in the snapshot nearest its first sighting with today's.
        # The verdict describes metric movement only — it does not claim
        # the recommendation caused it.
        pending=db.execute('''SELECT f.id,f.campaign_id,f.rule_code,f.first_seen_at
            FROM advisor_findings f LEFT JOIN advisor_outcomes o ON o.finding_id=f.id
            WHERE f.org_id=? AND f.account_id=?
              AND o.finding_id IS NULL AND f.first_seen_at<=?''',
            (acc['org_id'],acc['id'],now-7*DAY)).fetchall()
        snaps=db.execute('''SELECT taken_at,campaigns_json FROM advisor_snapshots
            WHERE org_id=? AND account_id=? ORDER BY taken_at''',
            (acc['org_id'],acc['id'])).fetchall()
        current_by_id={str(c.get('id')):c for c in campaigns}
        for f in pending:
            if f['campaign_id']=='ACCOUNT' or not snaps:
                continue
            nearest=min(snaps,key=lambda s:abs(s['taken_at']-f['first_seen_at']))
            base_list=_json.loads(nearest['campaigns_json'])
            base=next((c for c in base_list if str(c.get('id'))==f['campaign_id']),None)
            current=current_by_id.get(f['campaign_id'])
            if base is None or current is None:
                continue
            verdict=optimization_playbook.verify_outcome(base,current,f['rule_code'])
            db.execute('INSERT OR IGNORE INTO advisor_outcomes(finding_id,verdict,checked_at) VALUES(?,?,?)',
                       (f['id'],verdict,now))
        db.execute('''UPDATE advisor_scan_runs SET last_success_at=?,error_code=''
                      WHERE org_id=? AND account_id=?''',(now,acc['org_id'],acc['id']))
    # Compact digest of what is now open on this account (counts by level +
    # the new codes with their catalog titles). Computed from the rows this
    # scan just wrote; local only.
    digest = findings_digest(acc['org_id'], acc['id'], new_codes=new_codes)
    if new_codes:
        # One batched, opt-in Telegram alert per scan for genuinely new (or
        # re-opened) findings only. Rule codes, level counts and the
        # internal account number only: no campaign IDs, account labels or
        # credentials — finding titles stay local (digest/UI), they are not
        # pushed to Telegram.
        counts = digest['active_counts']
        await notify_telegram(
            f"LHM Ads AI: {len(new_codes)} cảnh báo quảng cáo mới trên {acc['platform']} "
            f"(account #{acc['id']}): {', '.join(new_codes)}. "
            f"Đang mở trên tài khoản: {counts['critical']} critical, "
            f"{counts['review']} review, {counts['opportunity']} opportunity "
            f"(tổng {digest['active_total']}). Mở ứng dụng để xem chi tiết.")
    return {'scanned':True,'reason':'ok','recommendations':len(suggestions),
            'digest':digest,
            'note':'Phát hiện bằng quy tắc đọc dữ liệu, KHÔNG thay đổi giá thầu hoặc ngân sách.'}


@app.get('/api/advisor/status')
def advisor_status(ident=Depends(require('admin','operator','reader'))):
    init_advisor_db()
    with connection() as db:
        rows=db.execute('''SELECT a.id,a.account_id,ac.label AS account_label,ac.platform,
            a.campaign_id,a.rule_code,a.severity,a.message,a.detail,a.first_seen_at,a.last_seen_at,
            a.acknowledged_at,a.resolved_at,o.verdict AS outcome FROM advisor_findings a
            LEFT JOIN advisor_outcomes o ON o.finding_id=a.id
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

class GrowthReadinessRequest(BaseModel):
    """Verified observations supplied by the authenticated local operator."""
    account_id: int = Field(gt=0)
    observation: dict = Field(default_factory=dict)


@app.post('/api/advisor/growth/readiness')
def growth_readiness(payload: GrowthReadinessRequest, ident=Depends(browser_admin)):
    """Read-only decision support. Never treats account metrics as verification."""
    from .growth_intelligence import assess_change_readiness

    license_required()
    acc = get_account(payload.account_id, ident['org_id'])
    if acc['platform'] not in ('google', 'meta'):
        raise HTTPException(422, 'Chỉ hỗ trợ Google Ads và Meta.')
    result = assess_change_readiness(payload.observation)
    # Explicitly disallow API writes, even if future skill versions change.
    return {
        'account_id': payload.account_id,
        'platform': acc['platform'],
        **result,
        'requires_human_approval': True,
        'may_write_ads': False,
        'source': 'operator_supplied_observation',
        'note': 'Thông tin đầu vào do người vận hành cung cấp; chưa được API tự xác minh.',
    }
