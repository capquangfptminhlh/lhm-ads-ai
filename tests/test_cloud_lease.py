"""Signed offline lease for the Windows app: Worker-signed (JS) leases verify in
Python, offline grace works, any server refusal or clock rollback hard-locks."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from ads_core import cloud_license as service
from ads_core.cloud_license import CloudLicense, CloudLicenseError, verify_lease

ROOT = Path(__file__).resolve().parents[1]
CUSTOMER = "e02ab0e4-c2b0-4a23-99a1-acd430b37fea"
LICENSE = "5b2f6a4e-1d0c-4b7e-9a3d-2f8e7c6b5a49"


def iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat().replace("+00:00", "Z")


@pytest.fixture()
def keys(monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setenv("LHM_LEASE_PUBLIC_KEY_B64", base64.b64encode(public).decode())
    return private


def sign(private, client_id: str, *, valid_until=None, plan_until=None, customer=CUSTOMER, issued=None):
    payload = {"v": 1, "customer_id": customer, "email": "owner@gmail.com", "license_id": LICENSE,
               "client_hash": hashlib.sha256(f"{LICENSE}:{client_id}".encode()).hexdigest(),
               "plan_code": "personal-1m", "seat_limit": 2,
               "license_expires_at": plan_until or iso(timedelta(days=20)),
               "issued_at": issued or iso(timedelta(0)), "valid_until": valid_until or iso(timedelta(hours=72))}
    b64 = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip("=")
    body = b64(json.dumps(payload).encode())
    return body + "." + b64(private.sign(body.encode()))


def test_worker_signed_lease_verifies_in_python(keys):
    """The exact bytes produced by workers/ads-api/src/commerce.js signLease()."""
    pkcs8 = keys.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption())
    client_id = str(uuid.uuid4())
    client_hash = hashlib.sha256(f"{LICENSE}:{client_id}".encode()).hexdigest()
    script = (
        "const {signLease}=await import(" + json.dumps((ROOT / "workers/ads-api/src/commerce.js").as_uri()) + ");"
        "const lease=await signLease({LEASE_SIGNING_KEY:" + json.dumps(base64.b64encode(pkcs8).decode()) + "},"
        "{customer:{id:" + json.dumps(CUSTOMER) + ",email:'owner@gmail.com'},"
        "license:{id:" + json.dumps(LICENSE) + ",expires_at:new Date(Date.now()+864e5).toISOString(),plan_code:'personal-1m',seat_limit:2},"
        "clientHash:" + json.dumps(client_hash) + "});console.log(lease);")
    lease = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True,
                           check=True, cwd=ROOT).stdout.strip()
    payload = verify_lease(lease, CUSTOMER, client_id)
    assert payload and payload["license_id"] == LICENSE
    # 72 h grace is capped by the plan ending in 24 h.
    assert payload["valid_until"] == payload["license_expires_at"]


def test_lease_rejects_tampering_other_pc_other_gmail_expiry_and_rollback(keys):
    client_id = str(uuid.uuid4())
    good = sign(keys, client_id)
    assert verify_lease(good, CUSTOMER, client_id)
    body, sig = good.split(".")
    assert verify_lease(body + "." + sig[:-2] + ("AA" if not sig.endswith("AA") else "BB"), CUSTOMER, client_id) is None
    assert verify_lease(good, CUSTOMER, str(uuid.uuid4())) is None          # copied to another PC
    assert verify_lease(good, str(uuid.uuid4()), client_id) is None         # another Gmail
    assert verify_lease(sign(keys, client_id, valid_until=iso(timedelta(minutes=-1))), CUSTOMER, client_id) is None
    assert verify_lease(sign(keys, client_id, plan_until=iso(timedelta(minutes=-1))), CUSTOMER, client_id) is None
    # Clock turned back a day: the PC has seen later trustworthy time.
    assert verify_lease(good, CUSTOMER, client_id, max_seen=time.time() + 86400) is None
    assert verify_lease(good, CUSTOMER, client_id, max_seen=time.time() + 60)


def test_no_public_key_means_no_offline_grace(tmp_path, monkeypatch):
    monkeypatch.delenv("LHM_LEASE_PUBLIC_KEY_B64", raising=False)
    assert verify_lease("a.b", CUSTOMER, str(uuid.uuid4())) is None


def paired(tmp_path) -> CloudLicense:
    native = CloudLicense(tmp_path)
    native.token = "a" * 64
    native.customer_id = CUSTOMER
    native.email = "owner@gmail.com"
    native._save()
    return native


def test_offline_grace_then_hard_lock_on_server_refusal(tmp_path, keys, monkeypatch):
    native = paired(tmp_path)
    lease = sign(keys, native.client_id)
    replies = [(200, {"active": True, "account_id": CUSTOMER, "account_email": "owner@gmail.com",
                      "seat_limit": 2, "expires_at": iso(timedelta(days=20)), "lease": lease})]
    def fake(path, payload, authenticated=False):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(native, "_request", fake)
    assert native.refresh_lease(mode="attach")["active"] is True
    assert native.lease == lease
    # Survives a restart (DPAPI/dev file) and works offline on the lease alone.
    again = CloudLicense(tmp_path)
    assert again.lease == lease and again.active() is True
    native.last_seen = 0
    replies.append(CloudLicenseError("offline"))
    offline = native.refresh_lease()
    assert offline["active"] is True and offline["reason"] == "OFFLINE" and offline["offline_until"]
    # The server says the plan expired: grace ends immediately, persisted too.
    replies.append((402, {"code": "SUBSCRIPTION_EXPIRED"}))
    assert native.refresh_lease()["reason"] == "SUBSCRIPTION_EXPIRED"
    assert native.active() is False
    assert CloudLicense(tmp_path).active() is False


def test_seat_limit_lists_devices_and_takeover_is_explicit(tmp_path, keys, monkeypatch):
    native = paired(tmp_path)
    sent = []
    def fake(path, payload, authenticated=False):
        sent.append(payload["mode"])
        if payload["mode"] == "attach":
            return 409, {"code": "SEAT_LIMIT", "devices": [{"label": "Chrome Android", "last_seen_at": "2026-10-25T08:00:00Z"}]}
        return 200, {"active": True, "account_id": CUSTOMER, "account_email": "owner@gmail.com",
                     "seat_limit": 2, "expires_at": iso(timedelta(days=5))}
    monkeypatch.setattr(native, "_request", fake)
    result = native.refresh_lease(mode="attach")
    assert result["reason"] == "SEAT_LIMIT" and result["devices"][0]["label"] == "Chrome Android"
    assert native.refresh_lease(mode="takeover")["active"] is True
    assert sent == ["attach", "takeover"]


def test_gmail_mode_drives_every_feature_gate(tmp_path, keys, monkeypatch):
    """advisor/autopilot/monitoring/OpenRouter all call read_license(); in Gmail
    mode it must follow the Gmail plan, not the legacy offline license file."""
    from ads_core.licensing import read_license, license_required
    monkeypatch.setenv("LHM_CLOUD_LICENSE_MODE", "required")
    native = paired(tmp_path)
    monkeypatch.setattr(service, "_session", native)
    assert read_license()["active"] is False
    with pytest.raises(Exception):
        license_required()
    native.lease = sign(keys, native.client_id)
    status = read_license()
    assert status["active"] is True and status["mode"] == "gmail" and status["plan"] == "personal-1m"
    assert license_required()["active"] is True


def test_locked_pc_api_returns_the_lock_reason(tmp_path, keys, monkeypatch):
    import ads_core.desktop_cloud_license  # noqa: F401  (registers the middleware)
    from ads_core.extended import app
    monkeypatch.setenv("LHM_CLOUD_LICENSE_MODE", "required")
    native = paired(tmp_path)
    native.reason = "SUBSCRIPTION_EXPIRED"
    monkeypatch.setattr(service, "_session", native)
    client = TestClient(app, base_url="http://127.0.0.1")
    r = client.get("/api/accounts")
    assert r.status_code == 402 and r.json()["code"] == "SUBSCRIPTION_EXPIRED"
    native.reason = "ACCOUNT_BLOCKED"
    assert client.get("/api/accounts").status_code == 403
