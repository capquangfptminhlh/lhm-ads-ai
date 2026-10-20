"""Native desktop shell and safe OAuth handoff to system browser."""
import base64
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core import oauth_connect as oauth


@pytest.fixture
def windows_app(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'native.sqlite'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'W'*32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'S'*48)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('LHM_DESKTOP_MODE', '1')
    monkeypatch.setenv('PUBLIC_BASE_URL','http://localhost:8765')
    with TestClient(app, client=('127.0.0.1',12345)) as client:
        with connection() as db:
            db.execute('INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                      ('native@sample.test',hash_password('strong_password_123'), 'my-org', 'admin'))
        yield client


def test_native_shell_does_not_open_external_browser_as_main_ui():
    root=Path(__file__).resolve().parent.parent
    shell=(root/'windows/desktop_window.py').read_text(encoding='utf-8')
    launcher=(root/'windows/launcher.py').read_text(encoding='utf-8')
    assert "webview.create_window(" in shell
    assert "gui='edgechromium'" in shell
    assert "webview.start(" in shell
    assert "webbrowser.open(url)" not in launcher
    assert "open_browser_after_start(" not in launcher
    assert "open_oauth_url(" in shell
    assert "host='127.0.0.1'" in launcher or "host='127.0.0.1'" in shell


def test_oauth_bridge_only_allows_provider_login_urls(monkeypatch):
    from windows.desktop_window import DesktopBridge
    observed=[]
    monkeypatch.setattr('windows.desktop_window.webbrowser.open',lambda url,**kwargs: observed.append(url) or True)
    bridge=DesktopBridge()
    assert bridge.open_oauth_url('https://accounts.google.com/o/oauth2/v2/auth?client_id=x')
    assert bridge.open_oauth_url('https://www.facebook.com/v24.0/dialog/oauth?client_id=x')
    for url in ['https://phishing.com/evil','http://accounts.google.com/o/oauth2/v2/auth',
                'https://accounts.google.com.evil.invalid/o/oauth2/v2/auth',
                'https://www.facebook.com/bad/oauth','file:///C:/Windows/system.ini',
                'javascript:alert(1)']:
        assert bridge.open_oauth_url(url) is False
    assert len(observed)==2


def test_desktop_oauth_callback_external_browser_no_cookie(windows_app, monkeypatch):
    from ads_core import desktop_setup
    c=windows_app
    login=c.post('/api/login',json={'email':'native@sample.test','password':'strong_password_123'})
    assert login.status_code==200
    csrf=c.get('/api/me').json()['csrf']
    setup=c.put('/api/desktop/providers/google',
                headers={'X-CSRF-Token':csrf},
                json={'client_id':'0123456-native.apps.googleusercontent.com'})
    assert setup.status_code==200,setup.text
    started=c.post('/api/oauth/google/start',headers={'X-CSRF-Token':csrf})
    assert started.status_code==200, started.text
    state=parse_qs(urlsplit(started.json()['authorization_url']).query)['state'][0]

    class MockResponse:
        status_code=200
        def __init__(self,body): self.body=body
        def raise_for_status(self): pass
        def json(self): return self.body

    class Http:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return False
        async def post(self,url,**kwargs):
            if url.endswith('/token'):
                return MockResponse({'access_token':'test-access','refresh_token':'test-refresh'})
            raise AssertionError(url)
        async def get(self,url,**kwargs):
            assert url.endswith('customers:listAccessibleCustomers')
            return MockResponse({'resourceNames':['customers/1234567890']})
    monkeypatch.setattr(oauth.httpx,'AsyncClient', Http)

    # Separate system-browser cookie jar: callback contains no WebView session.
    external=TestClient(app,client=('127.0.0.1',33333))
    response=external.get('/api/oauth/google/callback',params={'state':state,'code':'one-time-auth-code'},follow_redirects=False)
    assert response.status_code==303,response.text
    assert response.headers['location']=='/oauth/finished?status=ready'
    done=external.get(response.headers['location'])
    assert done.status_code==200 and 'Quay lại' in done.text
    assert external.get('/api/oauth/pending').status_code==401

    pending=c.get('/api/oauth/pending').json()
    assert len(pending)==1
    assert pending[0]['accounts'][0]['id']=='1234567890'
    assert external.get('/api/oauth/google/callback',params={'state':state,'code':'again'}).status_code==400
    assert c.post('/api/oauth/pending/'+pending[0]['id']+'/import',
                  headers={'X-CSRF-Token':csrf},json={'account_ids':['1234567890']}).status_code==200


def test_desktop_callback_state_rejects_expired_session(windows_app):
    c=windows_app
    assert c.post('/api/login',json={'email':'native@sample.test','password':'strong_password_123'}).status_code==200
    csrf=c.get('/api/me').json()['csrf']
    assert c.put('/api/desktop/providers/google',headers={'X-CSRF-Token':csrf},
                 json={'client_id':'0123456-native.apps.googleusercontent.com'}).status_code==200
    started=c.post('/api/oauth/google/start',headers={'X-CSRF-Token':csrf})
    state=parse_qs(urlsplit(started.json()['authorization_url']).query)['state'][0]
    with connection() as db:
        db.execute('DELETE FROM sessions')
    external=TestClient(app,client=('127.0.0.1',33333))
    assert external.get('/api/oauth/google/callback',params={'state':state,'code':'x'}).status_code==403
