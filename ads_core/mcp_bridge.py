"""Opt-in, read-only local MCP credentials and strictly tenant-scoped tools.

No HTTP MCP transport, no remote write operations and no Google/Meta tokens in
tool outputs. The browser admin deliberately provisions a short-lived key once.
"""
from __future__ import annotations
import time
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from .app import app, browser_admin, summary
from .db import connection, audit
from .security import hash_secret, make_secret
from .report_dates import PERIODS

MAX_ACTIVE = 5

def init_mcp_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS mcp_read_tokens (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          token_hash TEXT NOT NULL UNIQUE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
          revoked_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_mcp_user ON mcp_read_tokens(user_id);
        """)

class TokenRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)

@app.get('/api/mcp/local/tokens')
def list_mcp_tokens(ident=Depends(browser_admin)):
    init_mcp_db()
    with connection() as db:
        rows=db.execute("""SELECT id,created_at,expires_at,revoked_at FROM mcp_read_tokens
            WHERE user_id=? ORDER BY id DESC LIMIT 20""",(ident['id'],)).fetchall()
    return {'transport':'stdio', 'mode':'read_only', 'tokens':[dict(row) for row in rows]}

@app.post('/api/mcp/local/tokens')
def create_mcp_token(body:TokenRequest, ident=Depends(browser_admin)):
    init_mcp_db()
    now=int(time.time())
    secret=make_secret('lhm_mcp_')
    with connection() as db:
        count=db.execute("""SELECT COUNT(*) c FROM mcp_read_tokens
            WHERE user_id=? AND revoked_at IS NULL AND expires_at>?""",(ident['id'],now)).fetchone()['c']
        if count>=MAX_ACTIVE:
            raise HTTPException(409,'Thu hồi một khóa MCP cũ trước khi tạo thêm')
        cur=db.execute("""INSERT INTO mcp_read_tokens(token_hash,user_id,created_at,expires_at)
            VALUES(?,?,?,?)""",(hash_secret(secret),ident['id'],now,now+body.days*86400))
        audit(db,ident,'mcp.token_created',f'Read-only MCP key #{cur.lastrowid} expires in {body.days} days')
    return {'id':cur.lastrowid,'token':secret,'expires_at':now+body.days*86400,
            'warning':'Chỉ hiện một lần. Lưu trong kho bí mật của MCP client, không gửi qua chat.'}

@app.delete('/api/mcp/local/tokens/{token_id}')
def revoke_mcp_token(token_id:int, ident=Depends(browser_admin)):
    init_mcp_db()
    with connection() as db:
        found=db.execute("""UPDATE mcp_read_tokens SET revoked_at=? WHERE id=? AND user_id=?
            AND revoked_at IS NULL""",(int(time.time()),token_id,ident['id']))
        if not found.rowcount:
            raise HTTPException(404,'Khóa MCP không tồn tại hoặc đã thu hồi')
        audit(db,ident,'mcp.token_revoked',f'Revoked local MCP key #{token_id}')
    return {'ok':True}

def resolve_mcp_identity(token):
    """Check on EVERY tool call so disabling a user or revoking a key works immediately."""
    if not isinstance(token,str) or not token.startswith('lhm_mcp_') or len(token)>160:
        raise PermissionError('Invalid MCP credentials')
    init_mcp_db()
    with connection() as db:
        row=db.execute("""SELECT u.id,u.email,u.org_id,u.role,u.disabled FROM mcp_read_tokens t
           JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.revoked_at IS NULL
           AND t.expires_at>?""",(hash_secret(token),int(time.time()))).fetchone()
    if not row or row['disabled'] or row['role'] not in ('admin','operator','reader'):
        raise PermissionError('MCP key expired, revoked or user disabled')
    return dict(row)

TOOL_SCHEMAS = [
    {'name':'lhm_accounts', 'description':'List authorized tenant Ads accounts (metadata only, never credentials)',
     'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
    {'name':'lhm_report', 'description':'Read tenant reports by authorized Google/Meta APIs; demo is explicitly labeled',
     'inputSchema':{'type':'object','properties':{'period':{'type':'string','enum':[x for x in PERIODS if x!='custom']}},
                    'additionalProperties':False}},
    {'name':'lhm_alerts', 'description':'Read latest monitoring alerts for the tenant without provider tokens',
     'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
]

async def run_read_tool(name, args, ident):
    if not isinstance(args,dict):
        raise ValueError('Tool arguments must be an object')
    allowed={'lhm_accounts':set(),'lhm_report':{'period'},'lhm_alerts':set()}
    if name not in allowed or set(args)-allowed[name]:
        raise ValueError('Unknown tool or arguments')
    if name=='lhm_accounts':
        with connection() as db:
            return {'accounts':[dict(x) for x in db.execute(
                """SELECT id,label,platform,currency,
                   CASE WHEN token_ciphertext IS NULL THEN 0 ELSE 1 END connected
                   FROM accounts WHERE org_id=? AND label NOT LIKE '[REVOKED]%' ORDER BY id""",
                (ident['org_id'],)).fetchall()]}
    if name=='lhm_report':
        period=args.get('period','yesterday')
        if period not in PERIODS or period=='custom':
            raise ValueError('Unsupported report date range')
        data=await summary(period=period,ident=ident)
        # Never leak API credentials, provider account IDs or provider raw exceptions.
        accounts=[]
        for a in data['accounts']:
            safe={'account_id':a['account_id'],'platform':a['platform'],
                  'label':a['label']}
            if 'result' in a:
                r=a['result']
                safe['metrics']={k:r.get(k) for k in
                  ('source','currency','spend','clicks','impressions','ctr','conversions','cpa','roas')}
            else:safe['error']='Could not retrieve report'
            accounts.append(safe)
        return {'period':data['period'],'date_from':data['date_from'],
                'date_to':data['date_to'],'totals':data['totals'],'accounts':accounts}
    from .monitoring import init_monitor_db
    init_monitor_db()
    with connection() as db:
        return {'alerts':[dict(x) for x in db.execute(
            """SELECT id,account_id,created_at,severity,code,message,resolved_at
               FROM monitor_alerts WHERE org_id=? ORDER BY id DESC LIMIT 30""",
            (ident['org_id'],)).fetchall()]}
