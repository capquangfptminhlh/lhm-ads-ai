"""One-time browser onboarding for the local Windows application.

Only the Windows launcher creates an ephemeral setup token. The token is delivered
to the user's own browser in the URL *fragment* (not sent in HTTP requests);
registration requires that token, localhost access, and an empty user database.
No setup endpoint is enabled on hosted/VPS deployments.
"""
import hmac
import os
from pathlib import Path
import re
import secrets
import time

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .app import app
from .db import connection, init_db
from .security import hash_password, hash_secret, make_secret

TOKEN = None
TOKEN_EXPIRES_AT = 0
STATIC = Path(__file__).resolve().parent.parent / 'static'


def desktop_only(request: Request):
    if os.getenv('LHM_DESKTOP_MODE') != '1':
        raise HTTPException(404, 'Not found')
    if request.client is None or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(403, 'Local access only')


def users_exist() -> bool:
    with connection() as db:
        return db.execute('SELECT EXISTS(SELECT 1 FROM users)').fetchone()[0] == 1


def prepare_first_run():
    """Called only by the Windows launcher, never by a remote request."""
    global TOKEN, TOKEN_EXPIRES_AT
    init_db()
    if users_exist():
        TOKEN = None
        TOKEN_EXPIRES_AT = 0
        return None
    TOKEN = secrets.token_urlsafe(48)
    TOKEN_EXPIRES_AT = time.monotonic() + 1800
    return TOKEN


@app.get('/setup', include_in_schema=False)
def setup_page(request: Request):
    desktop_only(request)
    if users_exist():
        return RedirectResponse('/studio', status_code=303)
    return FileResponse(STATIC / 'setup.html')


class FirstAdmin(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    token: str = Field(min_length=32, max_length=256)


@app.post('/api/desktop/first-run', include_in_schema=False)
def create_first_admin(body: FirstAdmin, request: Request):
    global TOKEN, TOKEN_EXPIRES_AT
    desktop_only(request)
    # No password/key is ever written to the log or GitHub.
    if not TOKEN or time.monotonic() > TOKEN_EXPIRES_AT or not hmac.compare_digest(TOKEN, body.token):
        raise HTTPException(403, 'Phiên thiết lập đã hết hạn. Hãy đóng ứng dụng và mở lại.')
    email = body.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, 'Email không hợp lệ')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT EXISTS(SELECT 1 FROM users)').fetchone()[0]:
            raise HTTPException(409, 'Máy đã có tài khoản quản trị')
        cur = db.execute(
            'INSERT INTO users(org_id,email,password_hash,role) VALUES(?,?,?,?)',
            ('main', email, hash_password(body.password), 'admin'),
        )
        raw_session = make_secret()
        csrf = make_secret()
        db.execute(
            'INSERT INTO sessions(hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
            (hash_secret(raw_session), cur.lastrowid, csrf, int(time.time()) + 86400),
        )
    TOKEN = None
    TOKEN_EXPIRES_AT = 0
    response = JSONResponse({'ok': True, 'next': '/studio'})
    response.set_cookie(
        'lhm_session', raw_session, httponly=True, samesite='strict',
        secure=False, max_age=86400, path='/',
    )
    return response
