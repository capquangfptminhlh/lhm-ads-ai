"""Customer backup privacy, integrity and recovery; entirely offline."""
import base64
from pathlib import Path
import sqlite3
from fastapi.testclient import TestClient
import pytest

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password,seal,unseal
from ads_core import secure_backup


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'data'/'lhm-ads.sqlite3'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'K'*32).decode())
    monkeypatch.setenv('SESSION_SECRET','s'*48)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setenv('LHM_DESKTOP_MODE','1')
    monkeypatch.setenv('PUBLIC_BASE_URL','http://localhost:8765')
    with TestClient(app,client=('127.0.0.1',44000)) as test:
        with connection() as db:
            db.execute("INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)",
                       ('admin@local.test',hash_password('strong_local_password'),'store-1','admin'))
            cipher=seal('SENSITIVE_META_ACCESS_TOKEN','acct:store-1:meta:act_1234567890')
            db.execute("INSERT INTO accounts(org_id,platform,label,external_id,token_ciphertext,currency) VALUES(?,?,?,?,?,?)",
                       ('store-1','meta','Customer store','act_1234567890',cipher,'VND'))
        yield test


def login(client):
    assert client.post('/api/login',json={'email':'admin@local.test','password':'strong_local_password'}).status_code==200
    return {'X-CSRF-Token':client.get('/api/me').json()['csrf']}


def test_export_needs_login_csrf_and_loopback(client,monkeypatch):
    path='/api/desktop/backup/export'
    password={'passphrase':'correct horse strong battery'}
    assert client.post(path,json=password).status_code==401
    csrf=login(client)
    assert client.post(path,json=password).status_code==403
    assert client.post(path,json={'passphrase':'short'},headers=csrf).status_code==422
    result=client.post(path,json=password,headers=csrf)
    assert result.status_code==200,result.text[:200] if result.status_code!=200 else ''
    assert result.content.startswith(secure_backup.MAGIC)
    assert result.headers['content-type']=='application/octet-stream'
    assert 'attachment;' in result.headers['content-disposition']
    assert b'SENSITIVE_META_ACCESS_TOKEN' not in result.content
    assert b'Customer store' not in result.content
    assert b'K'*32 not in result.content
    with pytest.raises(ValueError,match='Sai mật khẩu'):
        secure_backup.decrypt_snapshot(result.content,'wrong password enough length')
    swapped=bytearray(result.content)
    swapped[-10] ^= 1
    with pytest.raises(ValueError):
        secure_backup.decrypt_snapshot(bytes(swapped),password['passphrase'])
    monkeypatch.delenv('LHM_DESKTOP_MODE')
    assert client.post(path,json=password,headers=csrf).status_code==404


def test_backup_restore_new_machine_and_drop_sessions(client,tmp_path):
    csrf=login(client)
    raw=client.post('/api/desktop/backup/export',
                    headers=csrf,json={'passphrase':'password for private ads backup'}).content
    new=tmp_path/'new-PC'/'LHMAdsAI'
    assert secure_backup.restore_into_empty_directory(
        raw,'password for private ads backup',new)['license_transferred'] is False
    assert (new/'local-settings.json').exists()
    restored=new/'data'/'lhm-ads.sqlite3'
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
        row=db.execute('SELECT token_ciphertext FROM accounts WHERE org_id=?',
                       ('store-1',)).fetchone()
        assert unseal(row[0],'acct:store-1:meta:act_1234567890')=='SENSITIVE_META_ACCESS_TOKEN'
    assert not (new/'data'/'licensing').exists()
    assert not (new/'licensing').exists()
    with pytest.raises(FileExistsError):
        secure_backup.restore_into_empty_directory(raw,'password for private ads backup',new)
    with pytest.raises(ValueError):
        secure_backup.decrypt_snapshot(raw,'different backup password')


def test_readiness_only_admin_desktop_and_no_secrets(client,monkeypatch):
    path='/api/desktop/readiness'
    assert client.get(path).status_code==401
    login(client)
    result=client.get(path)
    assert result.status_code==200,result.text[:200]
    payload=result.json()
    assert payload['provider_account_counts']['meta']['credentials_saved']==1
    assert payload['ready_for_commercial_distribution'] is False
    statuses={z['code']:z['status'] for z in payload['checks']}
    assert statuses['live_api']=='not_verified'
    assert statuses['authenticode']=='not_verified'
    assert 'SENSITIVE_META_ACCESS_TOKEN' not in result.text
    assert 'act_1234567890' not in result.text
    assert 'Customer store' not in result.text
    assert 'MASTER_KEY' not in result.text
    monkeypatch.delenv('LHM_DESKTOP_MODE')
    assert client.get(path).status_code==404


def test_restore_rejects_already_populated_folder(client,tmp_path):
    csrf=login(client)
    raw=client.post('/api/desktop/backup/export',headers=csrf,
                    json={'passphrase':'a very long safety password'}).content
    target=tmp_path/'existing'
    target.mkdir()
    (target/'keep-me.txt').write_text('DO NOT ERASE',encoding='utf-8')
    with pytest.raises(FileExistsError):
        secure_backup.restore_into_empty_directory(raw,'a very long safety password',target)
    assert (target/'keep-me.txt').read_text(encoding='utf-8')=='DO NOT ERASE'
