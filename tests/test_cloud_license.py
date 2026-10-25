"""Local Windows Google license client, origin lock, DPAPI boundary, and API gate."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import time
from urllib.parse import urlsplit, parse_qs
import pytest
from fastapi.testclient import TestClient

from ads_core.cloud_license import CloudLicense, CloudLicenseError
from ads_core import cloud_license as service
from ads_core.extended import app
from windows.desktop_window import DesktopBridge


def test_native_google_login_pair_and_lease(tmp_path, monkeypatch):
    native = CloudLicense(tmp_path)
    assert native.state()["active"] is False
    seen = []
    def fake(path, payload, authenticated=False):
        seen.append((path, payload, authenticated))
        if path.endswith("/pair/start"):
            assert len(payload["verifier_hash"]) == 64
            return 201, {"pair_id": "e02ab0e4-c2b0-4a23-99a1-acd430b37fea",
                         "display_code": "123456",
                         "verify_url": "https://ads.lhmcrm.com/desktop/pair/?id=e02ab0e4-c2b0-4a23-99a1-acd430b37fea"}
        if path.endswith("/pair/claim"):
            assert hashlib.sha256(payload["verifier"].encode()).hexdigest() == seen[0][1]["verifier_hash"]
            return 200, {"desktop_token": "a"*64, "customer_id": "e02ab0e4-c2b0-4a23-99a1-acd430b37fea", "email": "owner@gmail.com"}
        if path.endswith("/seat"):
            assert authenticated is True
            return 200, {"active": True, "account_id": "e02ab0e4-c2b0-4a23-99a1-acd430b37fea", "account_email": "owner@gmail.com", "seat_limit": 3,
                         "expires_at": (datetime.now(timezone.utc)+timedelta(days=5)).isoformat()}
        return 200, {"ok": True}
    monkeypatch.setattr(native, "_request", fake)
    x = native.start_pairing()
    assert x["status"] == "pending" and x["code"] == "123456"
    assert native.poll_pairing()["status"] == "authorized"
    assert native.state()["active"] is False
    assert native.refresh_lease(heartbeat=False)["seat_limit"] == 3
    assert native.active()
    assert native.state()["email"] == "owner@gmail.com"
    assert native.path.exists()
    if os.name != 'nt':
        assert os.stat(native.path).st_mode & 0o077 == 0
    else:
        assert 'a'*64 not in native.path.read_text(encoding='utf8')
    assert CloudLicense(tmp_path).state()["paired"]
    native.last_seen = time.monotonic()-130
    assert native.active() is False
    native.logout()
    assert not native.state()["paired"]


def test_no_device_session_without_verifiable_pairing(tmp_path, monkeypatch):
    native = CloudLicense(tmp_path)
    monkeypatch.setattr(native, "_request", lambda *a, **k: (202, {"status": "pending"}))
    with pytest.raises(CloudLicenseError):
        native.poll_pairing()
    native.start_pairing = lambda: {"status": "pending"}
    native.pair_id = "e02ab0e4-c2b0-4a23-99a1-acd430b37fea"
    native.pair_verifier = "c"*64
    assert native.poll_pairing()["status"] == "pending"
    assert native.state()["active"] is False


def test_fail_closed_native_license_and_browser_bridge(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        CloudLicense(tmp_path, origin="http://localhost:8765")
    opened=[]
    monkeypatch.setattr("windows.desktop_window.webbrowser.open",
                        lambda url,**kwargs: opened.append(url) or True)
    b=DesktopBridge()
    accepted="https://ads.lhmcrm.com/desktop/pair/?id=e02ab0e4-c2b0-4a23-99a1-acd430b37fea"
    assert b.open_license_url(accepted) is True
    for attack in (
       "http://ads.lhmcrm.com/desktop/pair/?id=e02ab0e4-c2b0-4a23-99a1-acd430b37fea",
       "https://ads.lhmcrm.com.evil.invalid/desktop/pair/?id=e02ab0e4-c2b0-4a23-99a1-acd430b37fea",
       "https://ads.lhmcrm.com/desktop/pair/?id=e02ab0e4-c2b0-4a23-99a1-acd430b37fea&next=evil",
       "javascript:alert(1)"):
        assert b.open_license_url(attack) is False
    assert opened == [accepted]


def test_cloud_gate_blocks_ads_api_before_local_auth(tmp_path, monkeypatch):
    import base64
    monkeypatch.setenv("MASTER_KEY", base64.b64encode(b"P"*32).decode())
    monkeypatch.setenv("SESSION_SECRET", "S"*48)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ads.sqlite3"))
    monkeypatch.setenv("LHM_CLOUD_LICENSE_MODE", "required")
    native=CloudLicense(tmp_path)
    monkeypatch.setattr(service, "_session", native)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/accounts").status_code == 402
        assert client.post("/api/accounts", json={"platform": "demo"}).status_code == 402
        assert client.get("/api/me").status_code == 401
        assert client.get("/api/cloud-license/status").status_code == 404  # Native-only endpoint unavailable outside Windows mode
        native.token = "d"*64
        native.last_seen = time.monotonic()
        native.expires_at = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        # After valid lease check, old local-user auth still applies.
        assert client.get("/api/accounts").status_code == 401
