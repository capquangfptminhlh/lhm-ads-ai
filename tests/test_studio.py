"""Integration checks for private Studio, tenant policies, user management, CSV and assistant."""
import base64
import pytest
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'ads.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'x'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','s'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as c:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)',
                       ('owner@example.com',hash_password('strong_password_987654'),'tenant1','admin'))
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES(?,?,?,?)',
                       ('another@example.com',hash_password('strong_password_123456'),'tenant2','admin'))
        yield c

def login(c):
    assert c.post('/api/login',json={'email':'owner@example.com','password':'strong_password_987654'}).status_code==200
    me=c.get('/api/studio/me').json()
    assert me['id']>0 and me['csrf']
    return {'X-CSRF-Token':me['csrf']}

def add_demo(c,h,label='Demo cửa hàng'):
    r=c.post('/api/accounts',headers=h,json={'platform':'demo','label':label,'external_id':'demo123'})
    assert r.status_code==200,r.text
    return r.json()['id']

def test_studio_home_and_static(env):
    r=env.get('/',follow_redirects=False)
    assert r.status_code==307 and r.headers['location']=='/studio'
    assert 'Trợ lý quảng cáo AI' in env.get('/studio').text
    assert env.get('/static/studio.js').status_code==200
    assert env.get('/classic').status_code==404

def test_assistant_requires_login_csrf_and_labels_demo(env):
    assert env.post('/api/assistant/chat',json={'message':'Báo cáo'}).status_code==401
    h=login(env)
    add_demo(env,h)
    assert env.post('/api/assistant/chat',json={'message':'Báo cáo'}).status_code==403
    r=env.post('/api/assistant/chat',headers=h,json={'message':'Phân tích chi tiêu trong 7 ngày'})
    assert r.status_code==200,r.text
    assert r.json()['mode']=='analyst'
    assert 'DEMO' in r.json()['reply']
    assert 'ROAS' in r.json()['reply']
    assert r.json()['sources']==['demo']

def test_csv_escaped_and_private(env):
    h=login(env)
    add_demo(env,h,'=HYPERLINK("evil")')
    export=env.get('/api/export/reports')
    assert export.status_code==200
    assert '"\'=HYPERLINK' in export.text or "'=HYPERLINK" in export.text
    assert 'demo' in export.text
    assert env.get('/api/export/reports?period=bad').status_code==422
    # Tenant isolation: other users' accounts never appear in downloaded CSV.
    with connection() as db:
        db.execute("INSERT INTO accounts(org_id,platform,label,external_id) VALUES ('tenant2','demo','PRIVATE OTHER','otherdemo')")
    assert 'PRIVATE OTHER' not in env.get('/api/export/reports').text

def test_team_create_and_disable(env):
    h=login(env)
    r=env.post('/api/team',headers=h,json={'email':'staff@example.com','role':'operator'})
    assert r.status_code==200 and len(r.json()['temporary_password'])>=12
    staff_id=r.json()['id']
    assert len(env.get('/api/team').json())==2
    own_id=env.get('/api/studio/me').json()['id']
    assert env.post(f'/api/team/{own_id}/disable',headers=h).status_code==409
    assert env.post(f'/api/team/{staff_id}/disable',headers=h).status_code==200
    assert any(u['disabled'] for u in env.get('/api/team').json() if u['id']==staff_id)
    assert env.post('/api/login',json={'email':'staff@example.com','password':r.json()['temporary_password']}).status_code==401
    assert env.post('/api/team',headers=h,json={'email':'staff@example.com','role':'reader'}).status_code==409

def test_external_tool_routes_removed(env):
    h=login(env)
    for path in ('/mcp','/api/mcp/call','/api/keys','/api/keys/1234567890'):
        for method in ('get','post','delete'):
            assert getattr(env,method)(path,headers=h).status_code==404
    html=env.get('/studio').text.lower()
    script=env.get('/static/studio.js').text.lower()
    for name in ('mcp','/api/keys','/api/mcp/call'):
        assert name not in html
        assert name not in script
    assert env.get('/static/app.js').status_code==404
    assert env.get('/static/index.html').status_code==404

def test_old_keys_deleted_on_upgrade(env):
    from ads_core.db import init_db
    with connection() as db:
        db.execute('CREATE TABLE api_keys (hash TEXT PRIMARY KEY, user_id INTEGER)')
        db.execute("INSERT INTO api_keys VALUES ('oldhash', 1)")
    init_db()
    with connection() as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='api_keys'").fetchone()[0]==0
    assert env.get('/api/summary',headers={'Authorization':'Bearer lhm_old'}).status_code==401

def test_assistant_stays_local_with_old_key_set(env,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','unused-old-setting')
    h=login(env)
    add_demo(env,h)
    r=env.post('/api/assistant/chat',headers=h,json={'message':'Phân tích quảng cáo'})
    assert r.status_code==200
    assert r.json()['mode']=='analyst'
    assert 'không gửi dữ liệu' in r.json()['disclaimer']

def test_password_rotation_revokes_session(env):
    h=login(env)
    assert env.post('/api/me/password',headers=h,json={'old_password':'bad','new_password':'something_new_45678'}).status_code==403
    r=env.post('/api/me/password',headers=h,json={'old_password':'strong_password_987654','new_password':'something_new_45678'})
    assert r.status_code==200
    assert env.get('/api/studio/me').status_code==401
    assert env.post('/api/login',json={'email':'owner@example.com','password':'something_new_45678'}).status_code==200
