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
    # Derive both timestamps from one clock read; independent iso() calls can
    # yield a fixture that accidentally exceeds 72h by a few microseconds.
    issued_at = issued or iso(timedelta(0))
    expiry_at = valid_until or (datetime.fromisoformat(issued_at.replace("Z", "+00:00")) +
                                timedelta(hours=72)).isoformat().replace("+00:00", "Z")
    payload = {"v": 1, "customer_id": customer, "email": "owner@gmail.com", "license_id": LICENSE,
               "client_hash": hashlib.sha256(f"{LICENSE}:{client_id}".encode()).hexdigest(),
               "plan_code": "personal-1m", "seat_limit": 2,
               "license_expires_at": plan_until or iso(timedelta(days=20)),
               "issued_at": issued_at, "valid_until": expiry_at}
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


def test_even_validly_signed_lease_must_respect_72h_cap_and_subscription_end(keys):
    pc = str(uuid.uuid4())
    issued_at = datetime.now(timezone.utc)
    stamp = lambda instant: instant.isoformat().replace("+00:00", "Z")
    issued = stamp(issued_at)
    good = sign(keys, pc, issued=issued, valid_until=stamp(issued_at+timedelta(hours=72)))
    assert verify_lease(good, CUSTOMER, pc) is not None
    # Signature alone cannot override product policy (both checks run locally).
    overlong = sign(keys, pc, issued=issued, valid_until=stamp(issued_at+timedelta(hours=73)))
    assert verify_lease(overlong, CUSTOMER, pc) is None
    after_plan = sign(keys, pc, issued=issued, plan_until=stamp(issued_at+timedelta(days=1)),
                      valid_until=stamp(issued_at+timedelta(days=2)))
    assert verify_lease(after_plan, CUSTOMER, pc) is None
    before_issue = sign(keys, pc, issued=issued, valid_until=stamp(issued_at-timedelta(minutes=2)))
    assert verify_lease(before_issue, CUSTOMER, pc) is None


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
    signed = json.loads(base64.urlsafe_b64decode(lease.split(".")[0] + "=="))
    replies = [(200, {"active": True, "account_id": CUSTOMER, "account_email": "owner@gmail.com",
                      "seat_limit": 2, "expires_at": signed["license_expires_at"], "lease": lease})]
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


def test_cloudflare_transient_outages_keep_only_an_existing_signed_lease(tmp_path, keys, monkeypatch):
    native = paired(tmp_path)
    lease = sign(keys, native.client_id)
    signed = json.loads(base64.urlsafe_b64decode(lease.split(".")[0] + "=="))
    good = {"active": True, "account_id": CUSTOMER, "account_email": "owner@gmail.com",
            "seat_limit": 2, "expires_at": signed["license_expires_at"], "lease": lease}
    replies = [(200, good), (503, {"code": "TEMPORARY_ERROR"}),
               (429, {"code": "RATE_LIMITED"}), (408, {}),
               (502, {"error": "temporary Cloudflare edge failure"}),
               (403, {"code": "LICENSE_REVOKED"})]
    monkeypatch.setattr(native, "_request", lambda *args, **kwargs: replies.pop(0))
    assert native.refresh_lease(mode="attach")["active"] is True
    for status in (503, 429, 408, 502):
        result = native.refresh_lease()
        assert result["active"] is True and result["reason"] == "OFFLINE"
        assert result["offline_until"]
        assert native.lease == lease
        assert CloudLicense(tmp_path).active() is True
    # A definitive server denial overrides the grace period immediately.
    assert native.refresh_lease()["reason"] == "LICENSE_REVOKED"
    assert native.active() is False
    assert CloudLicense(tmp_path).active() is False


def test_no_signed_lease_cannot_unlock_during_transient_outage(tmp_path, keys, monkeypatch):
    native = paired(tmp_path)
    replies = [(503, {}), (429, {}), (200, ["malformed-not-json-object"])]
    monkeypatch.setattr(native, "_request", lambda *args, **kwargs: replies.pop(0))
    for _ in range(3):
        result = native.refresh_lease()
        assert result["active"] is False and result["reason"] == "OFFLINE_LOCKED"
        assert native.lease is None


@pytest.mark.parametrize("raw", [b"", b"not-json", b"[]", b"null", b'"plain-text"'])
def test_bad_http_200_json_does_not_kill_heartbeat_or_grant_access(tmp_path, monkeypatch, raw):
    native = paired(tmp_path)
    class InvalidResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, max_bytes): return raw
    monkeypatch.setattr(service, "urlopen", lambda request, timeout: InvalidResponse())
    with pytest.raises(CloudLicenseError, match="Invalid response"):
        native._request("/api/desktop/pair/start", {})
    assert native.refresh_lease()["active"] is False


def test_seat_limit_lists_devices_and_takeover_is_explicit(tmp_path, keys, monkeypatch):
    native = paired(tmp_path)
    seat_lease = sign(keys, native.client_id)
    signed = json.loads(base64.urlsafe_b64decode(seat_lease.split(".")[0] + "=="))
    sent = []
    def fake(path, payload, authenticated=False):
        sent.append(payload["mode"])
        if payload["mode"] == "attach":
            return 409, {"code": "SEAT_LIMIT", "devices": [{"label": "Chrome Android", "last_seen_at": "2026-10-25T08:00:00Z"}]}
        return 200, {"active": True, "account_id": CUSTOMER, "account_email": "owner@gmail.com",
                     "seat_limit": 2, "expires_at": signed["license_expires_at"], "lease": seat_lease}
    monkeypatch.setattr(native, "_request", fake)
    result = native.refresh_lease(mode="attach")
    assert result["reason"] == "SEAT_LIMIT" and result["devices"][0]["label"] == "Chrome Android"
    assert native.refresh_lease(mode="takeover")["active"] is True
    assert sent == ["attach", "takeover"]


def test_active_http_without_verified_matching_lease_must_not_unlock(tmp_path, keys, monkeypatch):
    native = paired(tmp_path)
    valid = sign(keys, native.client_id)
    signed = json.loads(base64.urlsafe_b64decode(valid.split(".")[0] + "=="))
    base = {"active": True, "account_id": CUSTOMER, "account_email": "owner@gmail.com",
            "seat_limit": 2, "expires_at": signed["license_expires_at"]}
    bad_responses = [
        base,  # no lease at all (e.g. Worker secret missing)
        {**base, "lease": "forged.invalid"},
        {**base, "lease": valid, "seat_limit": 5},  # unsigned response changes cannot increase seats
        {**base, "lease": valid, "expires_at": iso(timedelta(days=30))},
    ]
    replies = [(200, item) for item in bad_responses] + [(200, {**base, "lease": valid})]
    monkeypatch.setattr(native, "_request", lambda *args, **kwargs: replies.pop(0))
    for _ in bad_responses:
        result = native.refresh_lease(mode="attach")
        assert result == {"active": False, "reason": "LEASE_INVALID"}
        assert native.active() is False
        assert CloudLicense(tmp_path).active() is False
    assert native.refresh_lease(mode="attach")["active"] is True
    assert native.active() is True


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
