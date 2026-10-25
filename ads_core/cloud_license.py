"""Desktop-only Google subscription grant client.

Cloudflare sees only OAuth-verified customer license metadata and random seat IDs.
Ads credentials, Ads customer IDs, local SQLite and reports NEVER leave the PC.
The bearer grant is protected with DPAPI on Windows, separate from Ads token vaults.
"""
from __future__ import annotations

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
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
                raise CloudLicenseError("Desktop license file corrupt. Do not reset without approval") from exc

    def _save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        values = {"client_id": self.client_id, "desktop_token": self.token, "email": self.email,
                  "customer_id": self.customer_id}
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

    def refresh_lease(self, *, heartbeat: bool = True) -> dict:
        with self.lock:
            if not self.token:
                return {"active": False, "reason": "signin_required"}
            try:
                code, data = self._request("/api/auth/seat",
                    {"client_id": self.client_id, "mode": "heartbeat" if heartbeat else "attach"},
                    authenticated=True)
            except CloudLicenseError:
                return {"active": self.active(), "reason": "offline"}
            if code == 200 and data.get("active") is True:
                self.last_seen = time.monotonic()
                self.expires_at = str(data.get("expires_at") or "")
                return {"active": True, "expires_at": self.expires_at,
                        "seat_limit": int(data.get("seat_limit") or 1)}
            self.last_seen = 0
            if code == 401:
                self.token = None
                self.email = ""
                self.customer_id = None
                self._save()
            return {"active": False, "reason": str(data.get("code") or "subscription_inactive")}

    def active(self) -> bool:
        with self.lock:
            return bool(self.token and self.customer_id and self.last_seen and time.monotonic() - self.last_seen < 120
                        and self.expires_at and self._expires_ok())

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
                "expires_at": self.expires_at, "pairing": bool(self.pair_id)}

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
            self.pair_id = self.pair_verifier = self.display_code = None
            self._save()

def init_cloud_license(folder: Path) -> CloudLicense:
    global _session
    if _session is None:
        _session = CloudLicense(folder)
    return _session

def current_cloud_license():
    return _session

def licensing_required() -> bool:
    return os.environ.get("LHM_CLOUD_LICENSE_MODE", "").strip().lower() == "required"

def cloud_access_ok() -> bool:
    if not licensing_required():
        return True
    return bool(_session is not None and _session.active())

def heartbeat_loop(stop: threading.Event):
    while not stop.is_set():
        session = current_cloud_license()
        if session and session.token:
            session.refresh_lease(heartbeat=bool(session.last_seen))
        if stop.wait(55):
            break
