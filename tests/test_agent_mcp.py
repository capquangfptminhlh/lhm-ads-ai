"""Guardrails for outbound MCP, tenancy, vault and draft-only schedules."""
import base64
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core.security import hash_password
from ads_core.agent_mcp import _next_daily, run_one_due_job


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "agent.sqlite"))
    monkeypatch.setenv("MASTER_KEY", base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("SESSION_SECRET", "n" * 48)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "trusted-mcp.example.com")
    monkeypatch.setenv("MCP_READ_TOOLS_GOOGLE", "get_campaigns,get_insights")
    with TestClient(app) as client:
        with connection() as db:
            db.execute(
                "INSERT INTO users(org_id,email,password_hash,role) VALUES(?,?,?,?)",
                ("t1", "admin@company.test", hash_password("long_password_12345"), "admin"),
            )
            db.execute(
                "INSERT INTO users(org_id,email,password_hash,role) VALUES(?,?,?,?)",
                ("t2", "other@company.test", hash_password("long_password_88888"), "admin"),
            )
        yield client


def admin(client):
    r = client.post("/api/login", json={
        "email": "admin@company.test", "password": "long_password_12345",
    })
    assert r.status_code == 200
    return {"X-CSRF-Token": client.get("/api/studio/me").json()["csrf"]}


def payload(endpoint="https://trusted-mcp.example.com/mcp"):
    return {
        "platform": "google", "label": "Google chính",
        "endpoint": endpoint,
        "token": "secret-placeholder-token-should-never-be-logged",
    }


def test_auth_origin_validation_and_csrf(env):
    assert env.get("/api/automation/connections").status_code == 401
    assert env.post("/api/automation/connections", json=payload()).status_code == 401
    headers = admin(env)
    assert env.post("/api/automation/connections", json=payload()).status_code == 403
    for endpoint in (
        "http://trusted-mcp.example.com/mcp",
        "https://127.0.0.1/mcp",
        "https://evil.example.com/mcp",
        "https://trusted-mcp.example.com:8443/mcp",
        "https://trusted-mcp.example.com/mcp?key=bad",
        "https://trusted-mcp.example.com/mcp#fragment",
    ):
        r = env.post("/api/automation/connections", json=payload(endpoint), headers=headers)
        assert r.status_code == 422, (endpoint, r.text)


def test_token_encrypted_and_never_exposed(env):
    headers = admin(env)
    r = env.post("/api/automation/connections", headers=headers, json=payload())
    assert r.status_code == 200, r.text
    id_ = r.json()["id"]
    assert "secret-placeholder" not in r.text
    assert r.json()["status"] == "saved_unverified"
    with connection() as db:
        row = db.execute("SELECT * FROM mcp_connections WHERE id=?", (id_,)).fetchone()
        assert "secret-placeholder" not in row["secret_ciphertext"]
        assert row["endpoint"] == payload()["endpoint"]
    data = env.get("/api/automation/connections").json()
    assert len(data) == 1
    assert "secret_ciphertext" not in data[0]
    assert "token" not in data[0]
    assert env.post(f"/api/automation/connections/{id_}/read",
                    headers=headers,json={"tool":"remove_campaign","arguments":{}}).status_code == 403
    assert env.delete(f"/api/automation/connections/{id_}", headers=headers).status_code == 200
    with connection() as db:
        row = db.execute("SELECT * FROM mcp_connections WHERE id=?", (id_,)).fetchone()
        assert row["enabled"] == 0 and row["secret_ciphertext"] == ""


def test_draft_schedule_creates_no_live_ads(env):
    headers = admin(env)
    creation = env.post("/api/automation/jobs", headers=headers, json={
        "job_type": "campaign_draft", "title": "Phụ kiện điện thoại",
        "brief": "Lập kế hoạch bán phụ kiện điện thoại với ngân sách thử nghiệm 500k/ngày.",
        "hour_local": 8, "minute_local": 0,
    })
    assert creation.status_code == 200, creation.text
    job_id = creation.json()["id"]
    assert env.get("/api/automation/jobs").json()[0]["id"] == job_id
    with connection() as db:
        db.execute("UPDATE agent_jobs SET next_run=1 WHERE id=?", (job_id,))
    assert asyncio.run(run_one_due_job()) is True
    out = env.get("/api/automation/outputs").json()
    assert len(out) == 1
    assert out[0]["kind"] == "campaign_draft"
    body = json.loads(out[0]["body"])
    assert body["status"] == "DRAFT_ONLY"
    assert "CHƯA phải nội dung" in body["note"]
    assert asyncio.run(run_one_due_job()) is False
    assert env.delete(f"/api/automation/jobs/{job_id}", headers=headers).status_code == 200


def test_report_schedule_restricted_to_read_tools(env):
    headers = admin(env)
    id_ = env.post("/api/automation/connections", headers=headers,json=payload()).json()["id"]
    base = {
        "job_type": "report", "title": "Báo cáo tự động",
        "brief": "Đọc hiệu suất quảng cáo hàng ngày từ kết nối MCP",
        "connection_id": id_, "hour_local": 9, "minute_local": 15,
        "tool_args": {"period": "yesterday"},
    }
    assert env.post("/api/automation/jobs", headers=headers,
                    json={**base, "tool_name":"create_campaign"}).status_code == 403
    ok = env.post("/api/automation/jobs", headers=headers,
                  json={**base, "tool_name":"get_campaigns"})
    assert ok.status_code == 200, ok.text
    assert env.delete(f"/api/automation/connections/{id_}", headers=headers).status_code == 200
    assert env.get("/api/automation/jobs").json()[0]["enabled"] == 0


def test_tenant_separation(env):
    h=admin(env)
    id_=env.post("/api/automation/connections", headers=h, json=payload()).json()["id"]
    assert env.post("/api/login",json={
        "email":"other@company.test","password":"long_password_88888"}).status_code == 200
    h2={"X-CSRF-Token":env.get("/api/studio/me").json()["csrf"]}
    assert env.get("/api/automation/connections").json()==[]
    assert env.post(f"/api/automation/connections/{id_}/test",headers=h2).status_code==404
    assert env.delete(f"/api/automation/connections/{id_}",headers=h2).status_code==404


def test_next_run_vietnam_timezone():
    after=datetime(2026,10,20,8,0,0,tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    actual=_next_daily(8,0,after)
    rendered=datetime.fromtimestamp(actual,ZoneInfo("Asia/Ho_Chi_Minh"))
    assert rendered.date().isoformat()=="2026-10-21" and rendered.hour==8
