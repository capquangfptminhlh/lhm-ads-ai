"""LHM Ads AI Studio: private report analysis and staff management.

Uses existing tenant-scoped services; never exposes provider tokens to a model.
"""
import re
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from .app import app, browser_admin, identify, require, summary
from .db import audit, connection
from .security import hash_password, make_secret
from .agent_mcp import router as automation_router

app.include_router(automation_router)

STATIC = Path(__file__).resolve().parent.parent / 'static'
# Preserve old dashboard as /classic while making the redesigned studio the home.
app.router.routes[:] = [r for r in app.router.routes if not (isinstance(r, APIRoute) and r.path == '/')]

@app.get('/', include_in_schema=False)
def entry():
    return RedirectResponse('/studio', status_code=307)

@app.get('/studio', include_in_schema=False)
def studio():
    return FileResponse(STATIC / 'studio.html')

@app.get('/automation', include_in_schema=False)
def automation_view():
    return FileResponse(STATIC / 'automation.html')

class ChatInput(BaseModel):
    message: str = Field(min_length=2, max_length=1200)
    period: str = Field(default='last_7d', pattern=r'^(last_7d|yesterday)$')


def num(value):
    return f'{value:,.0f}'.replace(',', '.')


def grounded_answer(message, data):
    items = [x for x in data['accounts'] if 'result' in x]
    failed = [x for x in data['accounts'] if 'error' in x]
    if not items:
        return ('Chưa có số liệu có thể đọc. Hãy thêm tài khoản Demo để trải nghiệm, '
                'hoặc kết nối Meta/Google bằng API chính thức. Không có dữ liệu giả cho tài khoản thật.')
    currencies = {}
    for item in items:
        r = item['result']
        currencies.setdefault(r['currency'], []).append(item)
    parts = [f'Báo cáo {"hôm qua" if data["period"] == "yesterday" else "7 ngày gần nhất"} '
             f'từ {len(items)} tài khoản; {len(failed)} tài khoản chưa lấy được dữ liệu.']
    for currency, group in currencies.items():
        spend = sum(x['result']['spend'] for x in group)
        clicks = sum(x['result']['clicks'] for x in group)
        impressions = sum(x['result']['impressions'] for x in group)
        parts.append(f'{currency}: chi {num(spend)}, {num(clicks)} click, '
                     f'{num(impressions)} lần hiển thị; CTR {100 * clicks / impressions:.2f}%' if impressions else
                     f'{currency}: chi {num(spend)}, không có lượt hiển thị để tính CTR.')
        top = max(group, key=lambda x: x['result']['spend'])
        parts.append(f'Tài khoản chi nhiều nhất bằng {currency}: {top["label"]} ({num(top["result"]["spend"])}).')
    if any(x['result']['source'] == 'demo' for x in items):
        parts.append('Có DỮ LIỆU DEMO minh họa, không phải số liệu quảng cáo thật.')
    if failed:
        parts.append('Một số nguồn chưa hoạt động: ' + '; '.join(f'{x["label"]}: {str(x["error"])[:90]}' for x in failed[:3]))
    parts.append('Chưa có dữ liệu chuyển đổi/doanh thu nên không thể xác định CPA hay ROAS; không tự bật/tắt quảng cáo.')
    return '\n'.join(parts)

@app.post('/api/assistant/chat')
async def assistant_chat(payload: ChatInput, ident=Depends(require('admin', 'operator', 'reader'))):
    data = await summary(period=payload.period, ident=ident)
    explanation = grounded_answer(payload.message, data)
    # Analyze only on this VPS; never send reports to outside AI models.
    return {'reply':explanation,'mode':'analyst','sources':data['totals']['sources'],
            'disclaimer':'Phân tích trên VPS; không gửi dữ liệu cho AI bên ngoài.'}

class TeamInput(BaseModel):
    email: str = Field(min_length=5,max_length=254)
    role: str = Field(pattern=r'^(reader|operator|admin)$')

@app.get('/api/studio/me')
def studio_me(ident=Depends(identify)):
    return {'id':ident['id'],'email':ident['email'],'role':ident['role'],
            'org_id':ident['org_id'],'csrf':ident.get('csrf') if ident['auth_type']=='browser' else None}

@app.get('/api/team')
def team(ident=Depends(browser_admin)):
    with connection() as db:
        return [dict(row) for row in db.execute('SELECT id,email,role,disabled,created_at FROM users WHERE org_id=? ORDER BY id',(ident['org_id'],))]

@app.post('/api/team')
def add_user(payload: TeamInput, ident=Depends(browser_admin)):
    email = payload.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise HTTPException(422,'Email không hợp lệ')
    pwd = make_secret()[:28] + 'Z9!'
    with connection() as db:
        try:
            cur=db.execute('INSERT INTO users (org_id,email,role,password_hash) VALUES (?,?,?,?)',
                           (ident['org_id'],email,payload.role,hash_password(pwd)))
        except __import__('sqlite3').IntegrityError:
            raise HTTPException(409,'Email đã được sử dụng')
        audit(db,ident,'team.create',f'Created user #{cur.lastrowid} as {payload.role}')
    return {'id':cur.lastrowid,'temporary_password':pwd,'warning':'Mật khẩu chỉ hiện một lần; chuyển qua kênh riêng an toàn.'}

@app.post('/api/team/{user_id}/disable')
def disable_user(user_id:int, ident=Depends(browser_admin)):
    if user_id==ident['id']:
        raise HTTPException(409,'Không thể vô hiệu hóa chính tài khoản đang dùng')
    with connection() as db:
        cur = db.execute('UPDATE users SET disabled=1 WHERE id=? AND org_id=? AND disabled=0',(user_id,ident['org_id']))
        if cur.rowcount!=1:
            raise HTTPException(404,'Không tìm thấy người dùng đang hoạt động')
        db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
        audit(db,ident,'team.disable',f'Disabled user #{user_id} and revoked sessions')
    return {'ok':True}

class PasswordInput(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12,max_length=256)

@app.post('/api/me/password')
def change_password(body: PasswordInput, ident=Depends(require('admin','operator','reader'))):
    from .security import verify_password
    with connection() as db:
        u = db.execute('SELECT password_hash FROM users WHERE id=?',(ident['id'],)).fetchone()
        if not u or not verify_password(u['password_hash'],body.old_password):
            raise HTTPException(403,'Mật khẩu hiện tại không đúng')
        db.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(body.new_password),ident['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(ident['id'],))
        audit(db,ident,'auth.password_changed','Revoked all sessions on password change')
    return {'ok':True,'message':'Đổi mật khẩu thành công. Vui lòng đăng nhập lại.'}

@app.get('/api/export/reports')
async def export_report(period:str='last_7d', ident=Depends(require('admin','operator','reader'))):
    import csv, io
    if period not in ('last_7d','yesterday'):
        raise HTTPException(422,'Khoảng thời gian không hợp lệ')
    data=await summary(period=period,ident=ident)
    output=io.StringIO()
    writer=csv.writer(output)
    def safe(value):
        # Neutralize spreadsheet formula injection from account labels / API errors.
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
    writer.writerow(['account_id','label','platform','source','currency','date','spend','impressions','clicks','error'])
    for item in data['accounts']:
        if 'result' not in item:
            writer.writerow([safe(item['account_id']),safe(item['label']),safe(item['platform']),'','','','','','',safe(item['error'])])
        else:
            r=item['result']
            for day in r['daily']:
                writer.writerow([safe(item['account_id']),safe(item['label']),safe(item['platform']),safe(r['source']),safe(r['currency']),
                                 safe(day['date']),day['spend'],day['impressions'],day['clicks'],''])
    return Response(content='\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="lhm-ads-{period}.csv"'})
