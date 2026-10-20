from pathlib import Path
from fastapi.testclient import TestClient
from ads_core.extended import app
from ads_core.db import connection, init_db


def test_no_outbound_mcp_routes():
    paths={r.path for r in app.router.routes}
    assert '/automation' not in paths
    assert not any('/api/automation' in p or p=='/mcp' for p in paths)


def test_legacy_mcp_tables_removed_on_upgrade(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'old.sqlite'))
    init_db()
    with connection() as db:
        db.execute('CREATE TABLE mcp_connections (id INTEGER PRIMARY KEY,secret_ciphertext TEXT)')
        db.execute("INSERT INTO mcp_connections VALUES (1,'legacy-secret')")
        db.execute('CREATE TABLE agent_jobs (id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE agent_outputs (id INTEGER PRIMARY KEY)')
    init_db()
    with connection() as db:
        legacy=['mcp_connections','agent_jobs','agent_outputs']
        for t in legacy:
            assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone()[0]==0
