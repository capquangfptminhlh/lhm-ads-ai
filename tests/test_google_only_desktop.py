"""Real FastAPI integration: Google-only PC first run and tenant-isolated Ads."""
import base64
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from datetime import datetime, timedelta, timezone
import time

import pytest
from fastapi.testclient import TestClient

from ads_core.extended import app
from ads_core.db import connection
from ads_core import cloud_license as grants
from ads_core import desktop_cloud_license as native_routes

CID_A = "e02ab0e4-c2b0-4a23-99a1-acd430b37fea"
CID_B = "6e768f7e-30cc-4f45-a55a-f481a04a29a4"
PROOF = "local-native-proof-only-" + "A" * 48


def grant_signed_lease(session, signer):
    now=datetime.now(timezone.utc)
    expiry=(now+timedelta(days=3)).isoformat().replace("+00:00","Z")
    valid=(now+timedelta(hours=72)).isoformat().replace("+00:00","Z")
    license_id="5b2f6a4e-1d0c-4b7e-9a3d-2f8e7c6b5a49"
    claims={"v":1,"customer_id":session.customer_id,"email":session.email,
            "license_id":license_id,
            "client_hash":hashlib.sha256(f"{license_id}:{session.client_id}".encode()).hexdigest(),
            "plan_code":"personal-1m","seat_limit":2,"license_expires_at":expiry,
            "issued_at":now.isoformat().replace("+00:00","Z"),"valid_until":valid}
    body=base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    session.lease=body+"."+base64.urlsafe_b64encode(signer.sign(body.encode())).decode().rstrip("=")
    session.expires_at=expiry


@pytest.fixture
def active_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "tenant.sqlite3"))
    monkeypatch.setenv("MASTER_KEY", base64.b64encode(b"N"*32).decode())
    monkeypatch.setenv("SESSION_SECRET", "S"*48)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("LHM_DESKTOP_MODE", "1")
    monkeypatch.setenv("LHM_CLOUD_LICENSE_MODE", "required")
    session = grants.CloudLicense(tmp_path)
    session.token = "e"*64
    session.customer_id = CID_A
    session.email = "alice@gmail.com"
    session.last_seen = time.monotonic()
    signer=Ed25519PrivateKey.generate()
    pub=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    monkeypatch.setenv("LHM_LEASE_PUBLIC_KEY_B64",base64.b64encode(pub).decode())
    grant_signed_lease(session,signer)
    monkeypatch.setattr(grants, "_session", session)
    native_routes.set_native_proof(PROOF)
    with TestClient(app, base_url="http://localhost:8765", client=("127.0.0.1", 50432)) as client:
        yield client, session, signer
    native_routes.set_native_proof(None)


def test_google_only_no_local_password_and_proof_cannot_be_guessed(active_app):
    client, native, signer = active_app
    assert client.get("/api/accounts").status_code == 401
    assert client.get("/api/cloud-license/status").status_code == 401
    assert client.post("/api/cloud-license/local-session").status_code == 401
    assert client.post("/api/cloud-license/local-session",
                       headers={"X-LHM-Native-Proof": "guessed"}).status_code == 401
    assert client.post("/api/login", json={"email":"anything@gmail.com","password":"bogus"}).status_code == 403
    assert client.get("/setup", follow_redirects=False).status_code == 303
    r = client.post("/api/cloud-license/local-session", headers={"X-LHM-Native-Proof": PROOF})
    assert r.status_code == 200, r.text
    assert "HttpOnly" in r.headers["set-cookie"]
    ident = client.get("/api/studio/me")
    assert ident.status_code == 200
    assert ident.json()["org_id"] == "google:"+CID_A


def test_customer_switch_never_reuses_ads_data(active_app):
    client, native, signer = active_app
    proof = {"X-LHM-Native-Proof": PROOF}
    assert client.post("/api/cloud-license/local-session",headers=proof).status_code == 200
    profile=client.get("/api/studio/me").json()
    account=client.post("/api/accounts",json={"platform":"demo","label":"My confidential demo","external_id":"demo-a"},
                        headers={"X-CSRF-Token": profile["csrf"]})
    assert account.status_code == 200,account.text
    assert len(client.get("/api/accounts").json())==1
    native.customer_id=CID_B
    native.email="bob@gmail.com"
    grant_signed_lease(native,signer)
    # Old cookies fail *before* any Ads route reads the database.
    assert client.get("/api/accounts").status_code == 401
    assert client.post("/api/cloud-license/local-session",headers=proof).status_code == 200
    profile_b=client.get("/api/studio/me").json()
    assert profile_b["email"]=="bob@gmail.com"
    assert profile_b["org_id"]=="google:"+CID_B
    assert client.get("/api/accounts").json()==[]
    with connection() as db:
        assert db.execute("SELECT COUNT(*) FROM accounts WHERE org_id=?",("google:"+CID_A,)).fetchone()[0]==1
    # Offline within 72h remains valid even without recent heartbeat.
    native.last_seen=0
    assert client.get("/api/accounts").status_code==200
    # Signed lease removal now locks hard, regardless of the old seat timestamp.
    native.lease=None
    assert client.get("/api/accounts").status_code==402
    assert client.post("/api/accounts",json={"platform":"demo","label":"blocked","external_id":"new"}).status_code==402
