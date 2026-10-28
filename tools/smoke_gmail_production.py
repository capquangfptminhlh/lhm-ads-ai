"""Read-only production acceptance for Gmail subscriptions and device-only Ads.

Unlike the older commerce connectivity probe, this refuses to pass while the
live Worker still serves a pilot-only password/key PWA. No login, money movement,
customer data or Ads credentials are involved.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlsplit
from pathlib import Path

# Support both "python tools/smoke_gmail_production.py" and package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import smoke_production

REQUIRED_FLAGS = (
    "commerce_binding_present",
    "commerce_schema_ready",
    "commerce_access_configured",
    "commerce_admin_config_ready",
    "google_login_configured",
    "google_seats_schema_ready",
    "desktop_pairing_schema_ready",
    "gmail_plans_schema_ready",
    "desktop_lease_signing_configured",
    "payment_instructions_configured",
)



def validate_base_url(value: str) -> str:
    """Only probe HTTPS LHM domains or a Cloudflare preview, never an arbitrary host.

    Reject paths, credentials and fragments so the checked routes cannot be
    silently rewritten by a crafted URL. No tokens/cookies are sent.
    """
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ch.isspace() for ch in value):
        raise ValueError("Origin must be a valid HTTPS LHM/Cloudflare URL")
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Origin is malformed") from exc
    trusted = (hostname == "lhmcrm.com" or hostname.endswith(".lhmcrm.com")
               or hostname.endswith(".workers.dev") or hostname.endswith(".pages.dev"))
    if (parsed.scheme != "https" or not trusted or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or port not in (None, 443)):
        raise ValueError("Only HTTPS LHM or Cloudflare preview origins are allowed")
    return "https://" + parsed.netloc.rstrip("/")


def audit(call=smoke_production.call) -> list[str]:
    issues: list[str] = []

    def fetch_json(path):
        try:
            status, body = call(path)
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
            return status, data
        except (ValueError, TypeError, OSError) as exc:
            issues.append(f"{path}: unreadable JSON response ({type(exc).__name__})")
            return None, {}

    status, readiness = fetch_json("/api/_hosting/status")
    if status != 200:
        issues.append("/api/_hosting/status must return HTTP 200")
    for name in REQUIRED_FLAGS:
        if readiness.get(name) is not True:
            issues.append(f"Live Gmail commerce not ready: {name}")

    status, user = fetch_json("/api/auth/session")
    if status != 401 or user.get("code") != "SIGNIN_REQUIRED":
        issues.append("Gmail session route missing or not correctly protected")

    status, config = fetch_json("/api/public/ads-config")
    if status != 200:
        issues.append("PWA Google/Meta public OAuth configuration endpoint unavailable")
    elif not (config.get("google_client_id") and config.get("meta_app_id")):
        issues.append("PWA Google/Meta OAuth public client IDs are not configured")

    try:
        status, page = call("/local/")
        if status != 200 or "Đăng nhập bằng Google" not in page:
            issues.append("Live PWA still shows pilot login or lacks Google sign-in")
    except (OSError, ValueError, TypeError) as exc:
        issues.append(f"Live PWA unavailable ({type(exc).__name__})")
    return issues


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only public Gmail/PWA readiness smoke for production or staging")
    parser.add_argument("--base-url", default=smoke_production.BASE,
                        help="HTTPS LHM domain or Cloudflare workers.dev/pages.dev preview origin")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable report (no secrets or customer data)")
    args = parser.parse_args(argv)
    try:
        base = validate_base_url(args.base_url)
    except ValueError as exc:
        parser.error(str(exc))
    # No redirect following, browser credentials or write operations.
    problems = audit(call=lambda path: smoke_production.call(path, base=base))
    if args.json:
        print(json.dumps({
            "base_url": base, "status": "FAIL" if problems else "PASS",
            "issues": problems,
            "note": "Public control-plane only; live OAuth/payment/Ads acceptance remains NOT_RUN",
        }, ensure_ascii=False, indent=2))
    else:
        for message in problems:
            print("FAIL: " + message)
        if problems:
            print("RESULT: GMAIL ENVIRONMENT NOT READY")
        else:
            print("PASS: public Gmail control-plane routes configured and protected.")
            print("NOTE: real Google OAuth, device leases, bank receipts and Ads still require live acceptance.")
    return 1 if problems else 0

if __name__ == "__main__":
    raise SystemExit(main())
