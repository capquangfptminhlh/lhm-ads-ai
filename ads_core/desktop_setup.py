"""Local-only provider app settings.  No account/app secrets inside distributed EXE."""
import os
import re
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from .app import app, browser_admin
from .db import connection, audit
from .security import seal, unseal


def desktop_mode():
    return os.environ.get('LHM_DESKTOP_MODE') == '1'


def ensure_desktop():
    if not desktop_mode():
        raise HTTPException(404, 'Cấu hình riêng chỉ có trên máy Windows')


def init_desktop_db():
    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS desktop_app_credentials (
            org_id TEXT NOT NULL, platform TEXT NOT NULL,
            client_id TEXT NOT NULL, secret_ciphertext TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(org_id,platform))""")


def desktop_provider(org, provider):
    """Never return this complete dict to the browser."""
    if not desktop_mode():
        return None
    init_desktop_db()
    with connection() as db:
        row=db.execute('SELECT * FROM desktop_app_credentials WHERE org_id=? AND platform=?', (org,provider)).fetchone()
    if not row:
        return None
    return {'client_id':row['client_id'],
            'client_secret':unseal(row['secret_ciphertext'],f'desktop:{org}:{provider}') if row['secret_ciphertext'] else ''}


class DesktopProviderInput(BaseModel):
    client_id: str = Field(min_length=1,max_length=250)
    client_secret: str = Field(default='',max_length=512)


def public_summary(org):
    from .oauth_connect import callback_url
    google=desktop_provider(org,'google')
    meta=desktop_provider(org,'meta')
    return {
        'desktop':True,
        'google':{'configured':bool(google and google['client_id']),
                  'client_id':google['client_id'] if google else '',
                  'secret_saved':bool(google and google['client_secret']),
                  'callback_url':callback_url('google')},
        'meta':{'configured':bool(meta and meta['client_id'] and meta['client_secret']),
                'client_id':meta['client_id'] if meta else '',
                'secret_saved':bool(meta and meta['client_secret']),
                'callback_url':callback_url('meta'),
                'note':'Meta localhost OAuth dành cho ứng dụng Development; Live có thể đòi HTTPS và duyệt ads_read.'},
    }


@app.get('/api/desktop/providers')
def get_desktop_providers(ident=Depends(browser_admin)):
    ensure_desktop()
    return public_summary(ident['org_id'])


@app.put('/api/desktop/providers/{provider}')
def save_desktop_provider(provider: str, payload: DesktopProviderInput, ident=Depends(browser_admin)):
    ensure_desktop()
    if provider not in ('google','meta'):
        raise HTTPException(404,'Nền tảng không được hỗ trợ')
    cid=payload.client_id.strip()
    if provider=='google' and not re.fullmatch(r'[A-Za-z0-9._-]{8,200}\.apps\.googleusercontent\.com',cid):
        raise HTTPException(422,'Cần Google OAuth Client ID loại Desktop app')
    if provider=='meta' and not re.fullmatch(r'\d{5,40}',cid):
        raise HTTPException(422,'Meta App ID phải là số')
    init_desktop_db()
    with connection() as db:
        old=db.execute('SELECT * FROM desktop_app_credentials WHERE org_id=? AND platform=?',(ident['org_id'],provider)).fetchone()
        previous=old['secret_ciphertext'] if old and cid==old['client_id'] else None
        secret=payload.client_secret.strip()
        ciphertext=seal(secret,f'desktop:{ident["org_id"]}:{provider}') if secret else previous
        if provider=='meta' and not ciphertext:
            raise HTTPException(422,'Meta App riêng cần App Secret nhập trên máy của anh')
        db.execute("""INSERT INTO desktop_app_credentials(org_id,platform,client_id,secret_ciphertext)
            VALUES(?,?,?,?) ON CONFLICT(org_id,platform) DO UPDATE SET
            client_id=excluded.client_id, secret_ciphertext=excluded.secret_ciphertext,updated_at=CURRENT_TIMESTAMP""",
            (ident['org_id'],provider,cid,ciphertext))
        audit(db,ident,'desktop.oauth.configure',provider+' local app credentials configured')
    return public_summary(ident['org_id'])


@app.delete('/api/desktop/providers/{provider}')
def delete_desktop_provider(provider:str,ident=Depends(browser_admin)):
    ensure_desktop()
    if provider not in ('google','meta'):
        raise HTTPException(404,'Nền tảng không hỗ trợ')
    init_desktop_db()
    with connection() as db:
        db.execute('DELETE FROM desktop_app_credentials WHERE org_id=? AND platform=?',(ident['org_id'],provider))
        audit(db,ident,'desktop.oauth.remove',provider+' local app settings removed')
    return public_summary(ident['org_id'])
