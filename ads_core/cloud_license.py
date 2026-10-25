"""Desktop-only Google subscription grant client.

Cloudflare sees only OAuth-verified customer license metadata and random seat IDs.
Ads credentials, Ads customer IDs, local SQLite and reports NEVER leave the PC.
The bearer grant is protected with DPAPI on Windows, separate from Ads token vaults.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid
import hashlib

from .windows_vault import dpapi_decrypt, dpapi_encrypt

ORIGIN = "https://ads.lhmcrm.com"
IDENTIFIER = re.compile(r"^[a-f0-9]{64}$")
_session = None

class CloudLicenseError(RuntimeError):
    pass

class CloudLicense:
    def __init__(self, folder: Path, origin: str = ORIGIN):
        if origin != ORIGIN:
            raise ValueError("Cloud licensing requires the verified HTTPS LHM origin")
        self.folder = Path(folder)
        self.path = self.folder / "desktop-cloud-license.json"
        self.lock = threading.RLock()
        self.origin = origin
        self.token = None
        self.email = ""
        self.customer_id = None
        self.client_id = None
        self.pair_id = None
        self.pair_verifier = None
        self.display_code = None
        self.last_seen = 0.0
        self.expires_at = ""
        self.lease = None
        self.max_seen = 0.0
        self.reason = ""
        self._load()

    def _load(self):
        with self.lock:
            if not self.path.exists():
                self.client_id = str(uuid.uuid4())
                self._save()
                return
            try:
                saved = json.loads(self.path.read_text(encoding="utf8"))
                if os.name == "nt":
                    if saved.get("format") != "windows-dpapi-v1":
                        raise CloudLicenseError("Desktop license grant requires DPAPI protection")
                    values = json.loads(dpapi_decrypt(saved["ciphertext"]).decode("utf8"))
                else:
                    if saved.get("format") != "dev-no-production-v1":
                        raise CloudLicenseError("Invalid dev license format")
                    values = saved["values"]
                self.client_id = str(uuid.UUID(values["client_id"], version=4))
                self.token = values.get("desktop_token")
                if self.token is not None and not IDENTIFIER.fullmatch(self.token):
                    raise ValueError("Invalid token")
                self.email = str(values.get("email") or "")
                cid = values.get("customer_id")
                self.customer_id = str(uuid.UUID(cid, version=4)) if cid else None
                if self.token and not self.customer_id:
                    # Older grants were not bound to a verified Google tenant.
                    self.token = None; self.email = ""
                lease = values.get("lease")
                self.lease = lease if isinstance(lease, str) and len(lease) < 4096 else None
                self.max_seen = float(values.get("max_seen") or 0.0)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
                raise CloudLicenseError("Desktop license file corrupt. Do not reset without approval") from exc

    def _save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        values = {"client_id": self.client_id, "desktop_token": self.token, "email": self.email,
                  "customer_id": self.customer_id, "lease": self.lease, "max_seen": self.max_seen}
        if os.name == "nt":
            payload = {"format": "windows-dpapi-v1",
                       "ciphertext": dpapi_encrypt(json.dumps(values).encode("utf8"))}
        else:
            # CI/dev only. Production Windows MUST use DPAPI.
            payload = {"format": "dev-no-production-v1", "values": values}
        temp = self.path.with_name(self.path.name + ".tmp")
        with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600),
                       "w", encoding="utf8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.path)
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    def _request(self, path: str, payload: dict, *, authenticated: bool = False) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if authenticated:
            if not self.token:
                raise CloudLicenseError("Please sign in using Google on the PC")
            headers["Authorization"] = "Bearer " + self.token
        request = Request(self.origin + path, json.dumps(payload).encode("utf8"),
                          headers=headers, method="POST")
        try:
            with urlopen(request, timeout=8) as response:
                data = response.read(4096)
                return response.status, json.loads(data.decode("utf8"))
        except HTTPError as exc:
            # HTTP status is useful; response must NOT include credentials.
            try:
                reply = json.loads(exc.read(4096).decode("utf8"))
            except (ValueError, UnicodeError):
                reply = {}
            return exc.code, reply
        except (URLError, TimeoutError, OSError) as exc:
            raise CloudLicenseError("Cannot contact LHM licensing over HTTPS") from exc

    def start_pairing(self) -> dict:
        with self.lock:
            self.pair_verifier = secrets.token_hex(32)
            challenge = hashlib.sha256(self.pair_verifier.encode("ascii")).hexdigest()
            status, data = self._request("/api/desktop/pair/start", {"verifier_hash": challenge})
            if status != 201 or not re.fullmatch(
                r"https://ads\.lhmcrm\.com/desktop/pair/\?id=[0-9a-f-]{36}",
                str(data.get("verify_url", ""))):
                raise CloudLicenseError("Secure browser pairing unavailable")
            self.pair_id = str(uuid.UUID(data["pair_id"], version=4))
            self.display_code = str(data.get("display_code") or "")
            return {"status": "pending", "url": data["verify_url"],
                    "code": self.display_code, "expires_in_seconds": 300}

    def poll_pairing(self) -> dict:
        with self.lock:
            if not self.pair_id or not self.pair_verifier:
                raise CloudLicenseError("Start PC sign-in first")
            status, data = self._request("/api/desktop/pair/claim",
                                         {"pair_id": self.pair_id, "verifier": self.pair_verifier})
            if status == 202:
                return {"status": "pending", "code": self.display_code}
            self.pair_id = None
            self.pair_verifier = None
            self.display_code = None
            token = data.get("desktop_token")
            if status != 200 or not isinstance(token, str) or not IDENTIFIER.fullmatch(token):
                raise CloudLicenseError("Pairing expired, account unpaid or already used")
            customer_id = data.get("customer_id")
            try:
                customer_id = str(uuid.UUID(customer_id, version=4))
            except (ValueError, TypeError, AttributeError):
                raise CloudLicenseError("Cloud license is not bound to a verified customer ID") from None
            self.token = token
            self.customer_id = customer_id
            self.email = str(data.get("email") or "")[:254]
            self.last_seen = 0
            self._save()
            return {"status": "authorized", "email": self.email}

    def refresh_lease(self, *, heartbeat: bool = True, mode: str | None = None) -> dict:
        """Ask the cloud for this PC's seat. mode: attach, heartbeat or takeover
        (takeover signs the least recently active device out; the user confirmed it)."""
        mode = mode or ("heartbeat" if heartbeat else "attach")
        if mode not in ("attach", "heartbeat", "takeover"):
            raise ValueError("Unknown seat mode")
        with self.lock:
            if not self.token:
                self.reason = "SIGNIN_REQUIRED"
                return {"active": False, "reason": self.reason}
            try:
                code, data = self._request("/api/auth/seat",
                    {"client_id": self.client_id, "mode": mode, "device_label": "Máy tính Windows"},
                    authenticated=True)
            except CloudLicenseError:
                # Offline: a valid signed lease keeps the PC usable until valid_until.
                self.reason = "OFFLINE" if self.active() else "OFFLINE_LOCKED"
                return {"active": self.active(), "reason": self.reason, "offline_until": self.offline_until()}
            if code == 200 and data.get("active") is True:
                # The cloud must confirm the same Google account on EVERY lease.
                # Do not trust an edited local identifier, even with a valid token.
                if (data.get("account_id") != self.customer_id or
                        str(data.get("account_email") or "").lower() != self.email.lower()):
                    self._drop_lease("GOOGLE_ACCOUNT_MISMATCH")
                    return {"active": False, "reason": self.reason}
                lease = data.get("lease")
                signed = verify_lease(lease, self.customer_id, self.client_id,
                                      max_seen=self.max_seen) if isinstance(lease, str) else None
                # A 200/active HTTP response is NOT proof of a paid subscription.
                # Check the actual Ed25519 lease, including the policy-bound plan
                # expiry and seat count, BEFORE updating local active status.
                if (signed is None or
                        data.get("expires_at") != signed.get("license_expires_at") or
                        data.get("seat_limit") != signed.get("seat_limit")):
                    self._drop_lease("LEASE_INVALID")
                    return {"active": False, "reason": self.reason}
                self.lease = lease
                self.last_seen = time.monotonic()
                self.expires_at = str(signed["license_expires_at"])
                self._observe_time(_lease_issued_at(lease))
                self.reason = ""
                self._save()
                return {"active": True, "expires_at": self.expires_at,
                        "seat_limit": signed["seat_limit"],
                        "offline_until": self.offline_until()}
            code_name = str(data.get("code") or "SUBSCRIPTION_INACTIVE")
            if code == 401:
                self.token = None
                self.email = ""
                self.customer_id = None
                code_name = "SIGNIN_REQUIRED"
            # Any refusal from the server ends offline grace immediately (hard lock).
            self._drop_lease(code_name)
            result = {"active": False, "reason": code_name}
            if code_name == "SEAT_LIMIT":
                result["devices"] = [
                    {"label": str(d.get("label") or "")[:60], "last_seen_at": str(d.get("last_seen_at") or "")[:40]}
                    for d in (data.get("devices") or [])[:20] if isinstance(d, dict)]
            return result

    def _drop_lease(self, reason: str):
        self.last_seen = 0
        self.lease = None
        self.reason = reason
        self._save()

    def _observe_time(self, extra: float | None = None):
        """Remember the latest trustworthy time seen so a rolled-back clock cannot
        stretch the offline grace period."""
        latest = max(time.time(), extra or 0)
        if latest > self.max_seen + 60:
            self.max_seen = latest

    def offline_until(self) -> str:
        payload = verify_lease(self.lease, self.customer_id, self.client_id, max_seen=self.max_seen) if self.lease else None
        return str(payload["valid_until"]) if payload else ""

    def active(self) -> bool:
        with self.lock:
            if not (self.token and self.customer_id):
                return False
            if self.last_seen and time.monotonic() - self.last_seen < SEAT_TTL_SECONDS and self.expires_at and self._expires_ok():
                return True
            return bool(self.lease and verify_lease(self.lease, self.customer_id, self.client_id,
                                                    max_seen=self.max_seen) is not None)

    def _expires_ok(self):
        from datetime import datetime, timezone
        try:
            parsed = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return parsed > datetime.now(timezone.utc)
        except ValueError:
            return False

    def state(self) -> dict:
        return {"active": self.active(), "paired": bool(self.token and self.customer_id),
                "customer_id": self.customer_id, "email": self.email,
                "expires_at": self.expires_at, "pairing": bool(self.pair_id),
                "reason": self.reason, "offline_until": self.offline_until()}

    def logout(self):
        with self.lock:
            if self.token:
                try:
                    self._request("/api/desktop/session/logout", {}, authenticated=True)
                except CloudLicenseError:
                    pass
            self.token = None
            self.email = ""
            self.customer_id = None
            self.last_seen = 0
            self.expires_at = ""
            self.lease = None
            self.reason = "SIGNIN_REQUIRED"
            self.pair_id = self.pair_verifier = self.display_code = None
            self._save()


SEAT_TTL_SECONDS = 600
HEARTBEAT_SECONDS = 300
ROLLBACK_TOLERANCE_SECONDS = 300
MAX_OFFLINE_LEASE_SECONDS = 72 * 3600


def _b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _lease_public_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from . import release_info
    raw = (getattr(release_info, "LEASE_PUBLIC_KEY_B64", "") or os.environ.get("LHM_LEASE_PUBLIC_KEY_B64", "")).strip()
    if not raw:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw, validate=True))
    except (ValueError, TypeError):
        return None


def _parse_time(value) -> float | None:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _lease_issued_at(lease: str | None) -> float | None:
    if not lease or "." not in lease:
        return None
    try:
        return _parse_time(json.loads(_b64url(lease.split(".", 1)[0]))["issued_at"])
    except (KeyError, TypeError, ValueError):
        return None


def verify_lease(lease: str | None, customer_id: str | None, client_id: str | None, *,
                 max_seen: float = 0.0, now: float | None = None) -> dict | None:
    """Return the lease payload if the Ed25519 signature, Gmail binding, this PC's
    seat, the plan expiry and the clock all check out; otherwise None."""
    key = _lease_public_key()
    if not key or not lease or not customer_id or not client_id or lease.count(".") != 1:
        return None
    body, signature = lease.split(".")
    try:
        key.verify(_b64url(signature), body.encode("ascii"))
        payload = json.loads(_b64url(body))
    except Exception:
        return None
    now = time.time() if now is None else now
    if now + ROLLBACK_TOLERANCE_SECONDS < max_seen:
        return None  # The clock was turned back.
    expected = hashlib.sha256((str(payload.get("license_id")) + ":" + client_id).encode()).hexdigest()
    valid_until = _parse_time(payload.get("valid_until"))
    plan_until = _parse_time(payload.get("license_expires_at"))
    issued = _parse_time(payload.get("issued_at"))
    if (payload.get("v") != 1 or payload.get("customer_id") != customer_id or payload.get("client_hash") != expected
            or not valid_until or not plan_until or not issued
            or valid_until <= issued
            or valid_until - issued > MAX_OFFLINE_LEASE_SECONDS
            or valid_until > plan_until
            or now + ROLLBACK_TOLERANCE_SECONDS < issued or now >= valid_until or now >= plan_until):
        return None
    return payload


_live = True

def init_cloud_license(folder: Path, *, live: bool = True) -> CloudLicense:
    """live=True for the window process that talks to the cloud; live=False for the
    background agent, which re-reads the lease the window process keeps current."""
    global _session, _live
    if _session is None:
        _session = CloudLicense(folder)
    _live = live
    return _session

def current_cloud_license():
    return _session

def licensing_required() -> bool:
    from . import release_info
    if getattr(release_info, "CLOUD_LICENSE_MODE", "") == "required":
        return True
    return os.environ.get("LHM_CLOUD_LICENSE_MODE", "").strip().lower() == "required"

def cloud_access_ok() -> bool:
    if not licensing_required():
        return True
    return entitlement()["active"]


def entitlement(folder: Path | None = None) -> dict:
    """Gmail-plan status for any process. The UI process uses its live session; a
    separate process (background agent, MCP) checks the signed lease on disk."""
    session = _session
    if session is not None and not _live:
        try:
            with session.lock:
                session._load()
        except CloudLicenseError:
            return {"active": False, "reason": "LICENSE_STATE_UNREADABLE"}
    if session is None:
        try:
            from .licensing import license_folder
            session = CloudLicense(folder or license_folder())
        except (CloudLicenseError, OSError):
            return {"active": False, "reason": "LICENSE_STATE_UNREADABLE"}
    with session.lock:
        active = session.active()
        return {"active": active, "reason": "" if active else (session.reason or "SUBSCRIPTION_REQUIRED"),
                "expires_at": session.expires_at or _lease_field(session, "license_expires_at"),
                "plan": _lease_field(session, "plan_code") or "gmail", "email": session.email,
                "offline_until": session.offline_until()}


def _lease_field(session: CloudLicense, field: str) -> str:
    payload = verify_lease(session.lease, session.customer_id, session.client_id, max_seen=session.max_seen) if session.lease else None
    return str(payload.get(field) or "") if payload else ""


def heartbeat_loop(stop: threading.Event):
    while not stop.is_set():
        session = current_cloud_license()
        if session and session.token:
            result = session.refresh_lease(heartbeat=bool(session.last_seen))
            # A seat that simply timed out (PC slept) is re-attached when there is room;
            # SEAT_LIMIT still waits for the user to choose "Dùng trên máy này".
            if result.get("reason") == "SEAT_REPLACED":
                session.refresh_lease(mode="attach")
        if stop.wait(HEARTBEAT_SECONDS):
            break
