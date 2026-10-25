"""Windows-only Google license activation endpoints and centralized API gate."""
from __future__ import annotations
import os
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from .app import app, browser_admin, identify
from .cloud_license import cloud_access_ok, current_cloud_license, licensing_required, CloudLicenseError

# These endpoints are only for local login/setup and licensing UI, NEVER Ads APIs.
PUBLIC_LICENSE_PREFIXES = ("/api/cloud-license/",)
UNLICENSED_BOOTSTRAP = {
    "/api/login", "/api/logout", "/api/me", "/api/studio/me",
    "/api/desktop/first-run", "/api/license"
}

@app.middleware("http")
async def require_online_subscription(request: Request, call_next):
    if not licensing_required() or not request.url.path.startswith("/api/"):
        return await call_next(request)
    path = request.url.path
    if path.startswith(PUBLIC_LICENSE_PREFIXES) or path in UNLICENSED_BOOTSTRAP:
        return await call_next(request)
    if not cloud_access_ok():
        return JSONResponse(
            {"error": "Subscription required. Sign in with Google and choose an active plan.",
             "code": "SUBSCRIPTION_REQUIRED"}, status_code=402,
            headers={"Cache-Control": "no-store"})
    return await call_next(request)

def license_client():
    if not licensing_required():
        raise HTTPException(404, "Cloud subscription is not enabled in this build")
    client = current_cloud_license()
    if client is None:
        raise HTTPException(503, "Cloud license client has not started")
    return client

@app.get("/api/cloud-license/status")
def cloud_license_status(ident=Depends(identify)):
    del ident
    return {"enabled": licensing_required(),
            **(current_cloud_license().state() if current_cloud_license() else
               {"active": False, "paired": False})}

@app.post("/api/cloud-license/start")
def cloud_license_start(ident=Depends(browser_admin)):
    del ident
    try:
        return license_client().start_pairing()
    except CloudLicenseError:
        raise HTTPException(503, "Cannot initiate secured Google sign in") from None

@app.post("/api/cloud-license/poll")
def cloud_license_poll(ident=Depends(browser_admin)):
    del ident
    try:
        client = license_client()
        result = client.poll_pairing()
        if result.get("status") == "authorized":
            license_status = client.refresh_lease(heartbeat=False)
            return {**result, **license_status}
        return result
    except CloudLicenseError:
        raise HTTPException(409, "PC sign in pending, expired or invalid") from None

@app.post("/api/cloud-license/attach")
def cloud_license_attach(ident=Depends(browser_admin)):
    del ident
    return license_client().refresh_lease(heartbeat=False)

@app.post("/api/cloud-license/logout")
def cloud_license_logout(ident=Depends(browser_admin)):
    del ident
    license_client().logout()
    return {"ok": True, "active": False}
