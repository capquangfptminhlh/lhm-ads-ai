"""Read-only production acceptance for Gmail subscriptions and device-only Ads.

Unlike the older commerce connectivity probe, this refuses to pass while the
live Worker still serves a pilot-only password/key PWA. No login, money movement,
customer data or Ads credentials are involved.
"""
from __future__ import annotations

import json
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


def main() -> int:
    problems = audit()
    if problems:
        for message in problems:
            print("FAIL: " + message)
        print("RESULT: GMAIL PRODUCTION NOT READY")
        return 1
    print("PASS: public Gmail control-plane routes configured and protected.")
    print("NOTE: real Google OAuth, device leases, bank receipts and Ads still require live acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
