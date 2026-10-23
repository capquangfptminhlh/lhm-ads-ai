"""Read-only MCP key isolation and JSON-RPC contract."""
import asyncio
import base64
import json
import pytest
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core.mcp_bridge import resolve_mcp_identity, run_read_tool
from ads_core.mcp_stdio import handle

@pytest.fixture
def mcp_client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'mcp-test.sqlite'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'x'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','s'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    with TestClient(app) as client:
        with connection() as db:
            db.execute("""INSERT INTO users(org_id,email,role,password_hash) VALUES(?,?,?,?)""",
                      ('tenantA','mcp-owner@example.com','admin',hash_password('long-test-password-123')))
            db.execute("""INSERT INTO users(org_id,email,role,password_hash) VALUES(?,?,?,?)""",
                      ('tenantB','other@example.com','admin',hash_password('long-test-password-123')))
            db.execute("""INSERT INTO accounts(org_id,platform,label,external_id,currency) VALUES(?,?,?,?,?)""",
                      ('tenantA','demo','Demo shop','demoA','VND'))
            db.execute("""INSERT INTO accounts(org_id,platform,label,external_id,currency) VALUES(?,?,?,?,?)""",
                      ('tenantB','demo','Private shop','demoB','VND'))
        assert client.post('/api/login',json={'email':'mcp-owner@example.com',
          'password':'long-test-password-123'}).status_code==200
        csrf=client.get('/api/studio/me').json()['csrf']
        yield client,{'x-csrf-token':csrf}

def test_key_requires_admin_and_csrf_and_is_revocable(mcp_client):
    client,h=mcp_client
    assert client.post('/api/mcp/local/tokens',json={'days':7}).status_code==403
    res=client.post('/api/mcp/local/tokens',headers=h,json={'days':7})
    assert res.status_code==200
    token=res.json()['token']
    assert token.startswith('lhm_mcp_')
    assert token not in str(client.get('/api/mcp/local/tokens').json())
    ident=resolve_mcp_identity(token)
    assert ident['org_id']=='tenantA'
    result=asyncio.run(handle({'jsonrpc':'2.0','id':1,'method':'tools/call',
          'params':{'name':'lhm_accounts','arguments':{}}},token))
    data=json.loads(result['result']['content'][0]['text'])
    assert len(data['accounts'])==1 and data['accounts'][0]['label']=='Demo shop'
    assert 'Private shop' not in str(data)
    blocked=asyncio.run(handle({'jsonrpc':'2.0','id':2,'method':'tools/call',
          'params':{'name':'pause_campaign','arguments':{}}},token))
    assert blocked['error']['code']==-32602
    assert client.delete('/api/mcp/local/tokens/'+str(res.json()['id']),headers=h).status_code==200
    assert asyncio.run(handle({'jsonrpc':'2.0','id':3,'method':'tools/list'},token))['error']['code']==-32001

def test_mcp_reports_only_supported_periods(mcp_client):
    client,h=mcp_client
    token=client.post('/api/mcp/local/tokens',headers=h,json={'days':1}).json()['token']
    ok=asyncio.run(handle({'jsonrpc':'2.0','id':'r','method':'tools/call',
       'params':{'name':'lhm_report','arguments':{'period':'yesterday'}}},token))
    assert ok['result']['isError'] is False
    report=json.loads(ok['result']['content'][0]['text'])
    assert report['totals']['contains_demo'] is True
    assert 'token_ciphertext' not in str(report)
    invalid=asyncio.run(handle({'jsonrpc':'2.0','id':1,'method':'tools/call',
       'params':{'name':'lhm_report','arguments':{'period':'custom'}}},token))
    assert invalid['error']['code']==-32602
    assert asyncio.run(handle({'jsonrpc':'2.0','id':2,'method':'initialize'},token))['result']['serverInfo']['name']=='lhm-ads-ai-local'

def test_password_change_revokes_all_local_mcp_keys(mcp_client):
    client,h=mcp_client
    res=client.post('/api/mcp/local/tokens',headers=h,json={'days':7})
    assert res.status_code==200
    token=res.json()['token']
    assert resolve_mcp_identity(token)['org_id']=='tenantA'
    updated=client.post('/api/me/password',headers=h,json={
      'old_password':'long-test-password-123',
      'new_password':'even-longer-test-password-456'})
    assert updated.status_code==200
    with pytest.raises(PermissionError):
        resolve_mcp_identity(token)
