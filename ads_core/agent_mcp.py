"""Outbound MCP connections and guarded daily advertising workflows.

No inbound MCP server. Never forward secrets to an LLM, no unsupervised write tools.
"""
import asyncio
import ipaddress
import json
import os
import re
import socket
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .app import browser_admin, require
from .db import connection, audit
from .security import seal, unseal

router = APIRouter(prefix="/api/automation", tags=["private-automation"])
TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def init_agent_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS mcp_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('google','meta')),
            label TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            secret_ciphertext TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mcp_connections_org ON mcp_connections(org_id);
        CREATE TABLE IF NOT EXISTS agent_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            connection_id INTEGER REFERENCES mcp_connections(id),
            job_type TEXT NOT NULL CHECK(job_type IN ('report','campaign_draft')),
            title TEXT NOT NULL,
            brief TEXT NOT NULL,
            tool_name TEXT,
            tool_args_json TEXT NOT NULL DEFAULT '{}',
            hour_local INTEGER NOT NULL CHECK(hour_local BETWEEN 0 AND 23),
            minute_local INTEGER NOT NULL CHECK(minute_local BETWEEN 0 AND 59),
            next_run INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            locked_until INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS agent_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            job_id INTEGER NOT NULL REFERENCES agent_jobs(id),
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_agent_outputs_org ON agent_outputs(org_id,id DESC);
        """)


def _allowed_url(raw):
    """Explicit hostname allowlist; https only; no localhost, IPs, redirects or non-443 ports."""
    parsed = urlsplit(raw)
    try:
        valid = (parsed.scheme == "https" and bool(parsed.hostname)
                 and not parsed.username and not parsed.password
                 and not parsed.fragment and not parsed.query
                 and parsed.port in (None, 443))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "MCP endpoint phải là URL HTTPS hợp lệ, cổng 443")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(hostname)
        raise HTTPException(422, "Không cho phép MCP endpoint bằng địa chỉ IP")
    except ValueError:
        pass
    allowed = {h.strip().lower() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()}
    if hostname not in allowed:
        raise HTTPException(422, "Tên miền MCP chưa được quản trị VPS cho phép (MCP_ALLOWED_HOSTS)")
    return raw, hostname


def _check_public_dns(hostname):
    """Defence in depth; egress firewall and DNS-pinning are also recommended."""
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise HTTPException(422, "Không phân giải được tên miền MCP")
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise HTTPException(422, "MCP endpoint trả về mạng nội bộ hoặc địa chỉ không công khai")


def _allowed_read_tools(platform):
    value = os.getenv("MCP_READ_TOOLS_" + platform.upper(), "")
    return {t.strip() for t in value.split(",") if re.fullmatch(r"[A-Za-z0-9_.\-/]{1,96}", t.strip())}


def _connection(row):
    return dict(row) if row else None


def _fetch_connection(connection_id, org_id):
    with connection() as db:
        row = db.execute(
            "SELECT * FROM mcp_connections WHERE id=? AND org_id=? AND enabled=1",
            (connection_id, org_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy kết nối MCP đang hoạt động")
    return dict(row)


def _secret_for(row):
    return unseal(row["secret_ciphertext"],
                  f"mcp:{row['org_id']}:{row['platform']}:{row['id']}")


@asynccontextmanager
async def mcp_session(row):
    """MCP Python SDK v2 supports the latest and earlier Streamable HTTP versions."""
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    url, hostname = _allowed_url(row["endpoint"])
    _check_public_dns(hostname)
    # No proxy from environment; no redirects to another origin.
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + _secret_for(row)},
        timeout=httpx2.Timeout(12, read=35),
        trust_env=False,
        follow_redirects=False,
    ) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def _tools(row):
    async with mcp_session(row) as session:
        found = await session.list_tools()
    return [
        {"name": t.name, "description": (t.description or "")[:200],
         "read_allowed": t.name in _allowed_read_tools(row["platform"])}
        for t in found.tools[:100]
    ]


async def _call_read(row, tool_name, args):
    if tool_name not in _allowed_read_tools(row["platform"]):
        raise HTTPException(403, "Công cụ này chưa được cho phép ở chế độ chỉ đọc")
    if len(json.dumps(args, ensure_ascii=False)) > 8000:
        raise HTTPException(422, "Tham số công cụ quá dài")
    async with mcp_session(row) as session:
        listed = await session.list_tools()
        if not any(t.name == tool_name for t in listed.tools):
            raise HTTPException(422, "MCP server không cung cấp công cụ đã chọn")
        result = await session.call_tool(tool_name, arguments=args)
    # Mark untrusted tool output as data; limit stored results.
    if result.isError:
        raise HTTPException(502, "MCP tool báo lỗi; kiểm tra tham số hoặc quyền đọc")
    body = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    if len(body) > 40000:
        raise HTTPException(422, "Kết quả quá lớn, hãy thu hẹp truy vấn")
    return body


class MCPCreate(BaseModel):
    platform: str = Field(pattern=r"^(google|meta)$")
    label: str = Field(min_length=2, max_length=80)
    endpoint: str = Field(min_length=12, max_length=500)
    token: str = Field(min_length=12, max_length=4096)


@router.get("/ai-status")
def local_ai_status(ident=Depends(require("admin", "operator", "reader"))):
    from .local_ai import ai_status
    return ai_status()


@router.get("/connections")
def connections(ident=Depends(require("admin", "operator", "reader"))):
    with connection() as db:
        return [dict(r) for r in db.execute(
            "SELECT id,platform,label,endpoint,enabled,created_at FROM mcp_connections "
            "WHERE org_id=? ORDER BY id DESC", (ident["org_id"],))]


@router.post("/connections")
def connect(payload: MCPCreate, ident=Depends(browser_admin)):
    endpoint, _ = _allowed_url(payload.endpoint.strip())
    with connection() as db:
        cur = db.execute(
            "INSERT INTO mcp_connections(org_id,platform,label,endpoint) VALUES(?,?,?,?)",
            (ident["org_id"], payload.platform, payload.label.strip(), endpoint),
        )
        connection_id = cur.lastrowid
        encrypted = seal(payload.token, f"mcp:{ident['org_id']}:{payload.platform}:{connection_id}")
        db.execute("UPDATE mcp_connections SET secret_ciphertext=? WHERE id=?",
                   (encrypted, connection_id))
        audit(db, ident, "mcp.connect", f"{payload.platform} connection #{connection_id}")
    return {"id": connection_id, "status": "saved_unverified",
            "message": "Đã mã hóa token. Hãy bấm Kiểm tra trước khi sử dụng."}


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: int, ident=Depends(browser_admin)):
    row = _fetch_connection(connection_id, ident["org_id"])
    try:
        tools = await _tools(row)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "MCP handshake thất bại. Kiểm tra URL, token, quyền và phiên bản server.")
    with connection() as db:
        audit(db, ident, "mcp.test", f"Connection #{connection_id}, {len(tools)} tools")
    return {"ok": True, "platform": row["platform"], "tools": tools,
            "read_allowlist": sorted(_allowed_read_tools(row["platform"])),
            "note": "Công cụ chỉ đọc phải được cho phép trong cấu hình VPS."}


@router.delete("/connections/{connection_id}")
def disconnect(connection_id: int, ident=Depends(browser_admin)):
    with connection() as db:
        updated = db.execute(
            "UPDATE mcp_connections SET enabled=0,secret_ciphertext='' "
            "WHERE id=? AND org_id=? AND enabled=1", (connection_id, ident["org_id"]))
        if updated.rowcount != 1:
            raise HTTPException(404, "Không tìm thấy kết nối")
        db.execute(
            "UPDATE agent_jobs SET enabled=0 WHERE connection_id=? AND org_id=?",
            (connection_id, ident["org_id"]))
        audit(db, ident, "mcp.revoke", f"Connection #{connection_id}; schedules disabled")
    return {"ok": True}


class ReadTool(BaseModel):
    tool: str = Field(min_length=1, max_length=96)
    arguments: dict = Field(default_factory=dict)


@router.post("/connections/{connection_id}/read")
async def read_tool(connection_id: int, payload: ReadTool,
                    ident=Depends(require("admin", "operator"))):
    row = _fetch_connection(connection_id, ident["org_id"])
    try:
        body = await _call_read(row, payload.tool, payload.arguments)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Không thể đọc dữ liệu MCP; kiểm tra quyền công cụ")
    with connection() as db:
        audit(db, ident, "mcp.read", f"{row['platform']} tool={payload.tool[:72]}")
    return {"source": "external_mcp_untrusted", "payload": json.loads(body)}


def _next_daily(hour, minute, after=None):
    now = (after or datetime.now(TZ)).astimezone(TZ)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return int(candidate.timestamp())


class JobCreate(BaseModel):
    job_type: str = Field(pattern=r"^(report|campaign_draft)$")
    title: str = Field(min_length=3, max_length=100)
    brief: str = Field(min_length=10, max_length=1500)
    connection_id: int | None = None
    tool_name: str | None = Field(default=None, max_length=96)
    tool_args: dict = Field(default_factory=dict)
    hour_local: int = Field(ge=0, le=23)
    minute_local: int = Field(ge=0, le=59)


@router.post("/jobs")
def create_job(payload: JobCreate, ident=Depends(browser_admin)):
    if payload.job_type == "report":
        if payload.connection_id is None or not payload.tool_name:
            raise HTTPException(422, "Lịch báo cáo cần kết nối MCP và công cụ chỉ đọc")
        row = _fetch_connection(payload.connection_id, ident["org_id"])
        if payload.tool_name not in _allowed_read_tools(row["platform"]):
            raise HTTPException(403, "Công cụ đọc không nằm trong danh sách đã cho phép")
    if len(json.dumps(payload.tool_args, ensure_ascii=False)) > 8000:
        raise HTTPException(422, "Tham số quá dài")
    with connection() as db:
        cur = db.execute(
            "INSERT INTO agent_jobs(org_id,connection_id,job_type,title,brief,tool_name,"
            "tool_args_json,hour_local,minute_local,next_run) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ident["org_id"], payload.connection_id, payload.job_type, payload.title,
             payload.brief, payload.tool_name,
             json.dumps(payload.tool_args), payload.hour_local, payload.minute_local,
             _next_daily(payload.hour_local, payload.minute_local)),
        )
        audit(db, ident, "job.create", f"Daily {payload.job_type} #{cur.lastrowid}")
    return {"id": cur.lastrowid, "status": "scheduled",
            "note": "Lịch chỉ tạo báo cáo hoặc nháp, không đăng và không chi tiền."}


@router.get("/jobs")
def list_jobs(ident=Depends(require("admin", "operator", "reader"))):
    with connection() as db:
        return [dict(r) for r in db.execute(
            "SELECT id,connection_id,job_type,title,hour_local,minute_local,next_run,enabled "
            "FROM agent_jobs WHERE org_id=? ORDER BY id DESC", (ident["org_id"],))]


@router.delete("/jobs/{job_id}")
def disable_job(job_id: int, ident=Depends(browser_admin)):
    with connection() as db:
        cur = db.execute(
            "UPDATE agent_jobs SET enabled=0 WHERE id=? AND org_id=? AND enabled=1",
            (job_id, ident["org_id"]))
        if cur.rowcount != 1:
            raise HTTPException(404, "Không tìm thấy lịch")
        audit(db, ident, "job.disable", f"Daily job #{job_id}")
    return {"ok": True}


@router.get("/outputs")
def outputs(ident=Depends(require("admin", "operator", "reader"))):
    with connection() as db:
        return [dict(r) for r in db.execute(
            "SELECT id,job_id,kind,status,body,created_at FROM agent_outputs "
            "WHERE org_id=? ORDER BY id DESC LIMIT 100", (ident["org_id"],))]


def _draft(brief):
    # A transparent template pending integration with an approved LLM.
    return json.dumps({
        "status": "DRAFT_ONLY", "brief": brief,
        "steps": ["Xác định mục tiêu, chuyển đổi và ngân sách",
                  "Nghiên cứu từ khóa (Google) hoặc mẫu nội dung (Meta)",
                  "Chuẩn bị nội dung, chính sách quảng cáo và thời gian chạy",
                  "Chờ admin duyệt trước khi tạo lên nền tảng"],
        "note": "Đây là khung kế hoạch tự động, CHƯA phải nội dung do mô hình AI sinh."
    }, ensure_ascii=False)


async def run_one_due_job(now=None):
    """Safely claim one due job; no writes to any advertising platform."""
    now = int(time.time() if now is None else now)
    with connection() as db:
        item = db.execute(
            "SELECT * FROM agent_jobs WHERE enabled=1 AND next_run<=? "
            "AND locked_until<=? ORDER BY next_run,id LIMIT 1", (now, now)
        ).fetchone()
        if item is None:
            return False
        cur = db.execute(
            "UPDATE agent_jobs SET locked_until=? WHERE id=? AND enabled=1 AND next_run<=? "
            "AND locked_until<=?", (now + 300, item["id"], now, now)
        )
        if cur.rowcount != 1:
            return False
        job = dict(item)
    from .local_ai import make_draft, analyze_report
    if job["job_type"] == "campaign_draft":
        platform = "google"
        if job["connection_id"]:
            try:
                platform = _fetch_connection(job["connection_id"], job["org_id"])["platform"]
            except HTTPException:
                pass
        plan = await make_draft(platform, job["brief"])
        content = (json.dumps({"status": "DRAFT_AI_REVIEW", "platform": platform,
                               "plan": plan, "warning": "Chưa xuất bản quảng cáo"},
                              ensure_ascii=False)
                   if plan else _draft(job["brief"]))
        kind = "campaign_ai_draft" if plan else "campaign_draft"
    else:
        try:
            row = _fetch_connection(job["connection_id"], job["org_id"])
            raw = await _call_read(row, job["tool_name"], json.loads(job["tool_args_json"]))
            analysis = await analyze_report(row["platform"], job["brief"], raw)
            content = (json.dumps({"analysis":analysis, "source":"untrusted_mcp", "raw":raw},
                                  ensure_ascii=False) if analysis else raw)
            kind = "mcp_ai_report" if analysis else "mcp_report_untrusted"
        except Exception:
            content = '{"error":"Không đọc được MCP; kiểm tra kết nối và công cụ"}'
            kind = "error"
    with connection() as db:
        db.execute(
            "INSERT INTO agent_outputs(org_id,job_id,kind,body) VALUES(?,?,?,?)",
            (job["org_id"], job["id"], kind, content[:40000]))
        db.execute(
            "UPDATE agent_jobs SET locked_until=0,next_run=? WHERE id=?",
            (_next_daily(job["hour_local"], job["minute_local"]), job["id"]))
    return True


async def scheduler_loop():
    while True:
        try:
            for _ in range(10):
                if not await run_one_due_job():
                    break
        except Exception:
            # Never log raw provider messages, tokens or tool payloads.
            pass
        await asyncio.sleep(60)
