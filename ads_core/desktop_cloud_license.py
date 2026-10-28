"""Windows Google-only local sign in and subscription enforcement.

Only the trusted pywebview window obtains the ephemeral native proof. Google
OAuth happens in the system browser, and advertising credentials never leave PC.
"""
from __future__ import annotations

import hmac
import os
import re
import time
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .app import app
from .cloud_license import current_cloud_license, licensing_required, cloud_access_ok, entitlement, CloudLicenseError
from .db import connection
from .security import hash_password, hash_secret, make_secret

_native_proof = None
BOOTSTRAP_ENDPOINTS = frozenset({
    "/api/cloud-license/status", "/api/cloud-license/start",
    "/api/cloud-license/poll", "/api/cloud-license/attach",
    "/api/cloud-license/logout", "/api/cloud-license/local-session",
})
UNLICENSED_ENDPOINTS = frozenset({
    "/api/logout", "/api/me", "/api/studio/me", "/api/license",
})
CLIENTS = frozenset({"localhost", "127.0.0.1"})
LOCK_MESSAGES = {
    "SUBSCRIPTION_REQUIRED": "Đăng nhập Google và mua gói còn hạn để dùng phần mềm",
    "PAYMENT_PENDING": "Đơn hàng đang chờ xác nhận thanh toán",
    "SUBSCRIPTION_EXPIRED": "Gói đã hết hạn. Gia hạn để tiếp tục; dữ liệu trên máy vẫn còn",
    "LICENSE_REVOKED": "Gói đã bị thu hồi. Liên hệ hỗ trợ",
    "ACCOUNT_BLOCKED": "Tài khoản đang bị tạm khoá. Liên hệ hỗ trợ",
    "SEAT_LIMIT": "Gmail này đang dùng trên đủ số máy của gói",
    "SEAT_REPLACED": "Gmail này vừa được dùng trên máy khác",
    "OFFLINE_LOCKED": "Đã quá thời gian dùng offline. Kết nối Internet để tiếp tục",
    "LEASE_INVALID": "Máy chủ chưa cấp được giấy phép hợp lệ. Kiểm tra cấu hình bản quyền hoặc liên hệ hỗ trợ",
}

def set_native_proof(proof: str | None):
    """Launcher sets a *per-process* random proof, never stored in DB or served in HTML."""
    global _native_proof
    if proof is not None and (not isinstance(proof, str) or len(proof) < 48):
        raise ValueError("Invalid native license bootstrap proof")
    _native_proof = proof

def verified_native_request(req: Request):
    if not licensing_required() or os.environ.get("LHM_DESKTOP_MODE") != "1":
        raise HTTPException(404, "Not available outside Windows Google license mode")
    if req.client is None or req.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Loopback access required")
    if req.url.hostname not in CLIENTS:
        raise HTTPException(403, "Untrusted host")
    origin = req.headers.get("origin")
    if origin and origin != f"{req.url.scheme}://{req.headers.get('host')}":
        raise HTTPException(403, "Origin mismatch")
    supplied = req.headers.get("x-lhm-native-proof") or ""
    if not _native_proof or not hmac.compare_digest(supplied, _native_proof):
        raise HTTPException(401, "Native window authentication required")

def client():
    session = current_cloud_license()
    if session is None:
        raise HTTPException(503, "Cloud licensing has not started")
    return session

@app.middleware("http")
async def require_online_subscription(request: Request, call_next):
    if not licensing_required() or not request.url.path.startswith("/api/"):
        return await call_next(request)
    path = request.url.path
    # In Google-only mode legacy passwords cannot issue a usable local session.
    if path in ("/api/login", "/api/desktop/first-run", "/api/license/activate"):
        return JSONResponse({"code": "GOOGLE_LOGIN_REQUIRED", "error": "Đăng nhập bằng Google"},
                            status_code=403, headers={"Cache-Control": "no-store"})
    if path.startswith("/api/cloud-license/") or path in UNLICENSED_ENDPOINTS:
        return await call_next(request)
    if not cloud_access_ok():
        # Hard lock: everything outside the sign-in/renewal allowlist is refused here,
        # whatever the UI shows. The code tells the window which screen to show.
        reason = entitlement().get("reason") or "SUBSCRIPTION_REQUIRED"
        message = LOCK_MESSAGES.get(reason, LOCK_MESSAGES["SUBSCRIPTION_REQUIRED"])
        return JSONResponse({"code": reason, "error": message},
                            status_code=403 if reason in ("LICENSE_REVOKED", "ACCOUNT_BLOCKED") else 402,
                            headers={"Cache-Control": "no-store"})
    return await call_next(request)

@app.get("/api/cloud-license/status")
def cloud_license_status(request: Request):
    verified_native_request(request)
    return {"enabled": True, **client().state()}

@app.post("/api/cloud-license/start")
def cloud_license_start(request: Request):
    verified_native_request(request)
    try:
        return client().start_pairing()
    except CloudLicenseError:
        raise HTTPException(503, "Không kết nối được tới máy chủ bản quyền") from None

@app.post("/api/cloud-license/poll")
def cloud_license_poll(request: Request):
    verified_native_request(request)
    try:
        native = client()
        result = native.poll_pairing()
        if result.get("status") == "authorized":
            return {**result, **native.refresh_lease(heartbeat=False)}
        return result
    except CloudLicenseError:
        raise HTTPException(409, "Phiên xác thực PC đã hết hạn hoặc chưa được phê duyệt") from None

@app.post("/api/cloud-license/attach")
async def cloud_license_attach(request: Request):
    verified_native_request(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    # "takeover" only after the user chose "Dùng trên máy này" on the device-limit screen.
    mode = "takeover" if isinstance(body, dict) and body.get("mode") == "takeover" else "attach"
    return client().refresh_lease(mode=mode)

@app.post("/api/cloud-license/logout")
def cloud_license_logout(request: Request):
    verified_native_request(request)
    native = client()
    native.logout()
    # Clear local cookie and invalidate sessions; no Ads encrypted data is deleted.
    with connection() as db:
        db.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE org_id LIKE 'google:%')")
    result = JSONResponse({"ok": True, "active": False})
    result.delete_cookie("lhm_session", path="/")
    return result

@app.post("/api/cloud-license/local-session")
def native_google_local_session(request: Request):
    """Exchange a verified active local CloudLicense for a same-origin FastAPI cookie.
    This is NOT the Google OAuth token and never grants cross-customer DB access.
    """
    verified_native_request(request)
    native = client()
    if not native.active() or not native.customer_id:
        raise HTTPException(402, "Gói bản quyền chưa kích hoạt hoặc phiên đã hết hạn")
    try:
        customer_uuid = str(uuid.UUID(native.customer_id, version=4))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(403, "Thông tin Gmail chưa được máy chủ xác nhận") from None
    email = native.email.lower().strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(403, "Gmail chưa được xác minh")
    org_id = "google:" + customer_uuid
    now = int(time.time())
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT id,email,disabled FROM users WHERE org_id=? LIMIT 1", (org_id,)).fetchone()
        if row:
            if row["disabled"]:
                raise HTTPException(403, "Tài khoản bị khóa")
            if row["email"] != email:
                duplicate = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                if duplicate:
                    raise HTTPException(409, "Gmail đã có dữ liệu cục bộ khác; cần sao lưu và chuyển đổi có kiểm soát")
                db.execute("UPDATE users SET email=? WHERE id=?", (email, row["id"]))
            user_id = row["id"]
        else:
            # Fail safely rather than silently inheriting a legacy user's encrypted Ads data.
            if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
                raise HTTPException(409, "Gmail đã dùng cho tài khoản cũ; cần di chuyển dữ liệu theo quy trình")
            random_secret = make_secret() + make_secret()
            cursor = db.execute(
                "INSERT INTO users(org_id,email,password_hash,role) VALUES(?,?,?,?)",
                (org_id, email, hash_password(random_secret), "admin"))
            user_id = cursor.lastrowid
        # Account switch cannot keep a prior Google user's local browser session.
        db.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE org_id LIKE 'google:%')")
        raw, csrf = make_secret(), make_secret()
        db.execute("INSERT INTO sessions(hash,user_id,csrf,expires_at) VALUES(?,?,?,?)",
                   (hash_secret(raw), user_id, csrf, now + 86400))
    response = JSONResponse({"ok": True, "email": email, "next": "/studio"})
    response.set_cookie("lhm_session", raw, httponly=True, samesite="strict",
                        secure=False, path="/", max_age=86400)
    return response
