"""Offline tests for read-only, fail-closed LIVE Gmail readiness probe."""
import json

from tools.smoke_gmail_production import REQUIRED_FLAGS, audit, main, validate_base_url
from tools import smoke_gmail_production


def healthy(path):
    if path == "/api/_hosting/status":
        return 200, json.dumps({name: True for name in REQUIRED_FLAGS})
    if path == "/api/auth/session":
        return 401, json.dumps({"code": "SIGNIN_REQUIRED"})
    if path == "/api/public/ads-config":
        return 200, json.dumps({"google_client_id": "oauth-test-client",
                                "meta_app_id": "public-test-meta-app"})
    if path == "/local/":
        return 200, "<h1>Đăng nhập bằng Google</h1>"
    raise AssertionError("Unexpected network route")


def test_ready_public_control_plane_has_no_errors():
    assert audit(healthy) == []


def test_old_pilot_production_does_not_falsely_pass():
    def pilot(path):
        if path == "/api/_hosting/status":
            return 200, '{"commerce_binding_present":true,"commerce_schema_ready":true}'
        if path in ("/api/auth/session", "/api/public/ads-config"):
            return 503, '{"code":"DEVICE_ONLY_NOT_READY"}'
        if path == "/local/":
            return 200, "<div>Kích hoạt lần đầu bằng key</div>"
        raise AssertionError("Unexpected route")
    problems = audit(pilot)
    assert "Live Gmail commerce not ready: google_login_configured" in problems
    assert "Gmail session route missing or not correctly protected" in problems
    assert "PWA Google/Meta public OAuth configuration endpoint unavailable" in problems
    assert "Live PWA still shows pilot login or lacks Google sign-in" in problems


def test_missing_bank_or_worker_signer_blocks_release():
    def missing(path):
        code, content = healthy(path)
        if path == "/api/_hosting/status":
            data = json.loads(content)
            data["payment_instructions_configured"] = False
            data["desktop_lease_signing_configured"] = False
            return code, json.dumps(data)
        return code, content
    result = audit(missing)
    assert any("payment_instructions_configured" in issue for issue in result)
    assert any("desktop_lease_signing_configured" in issue for issue in result)


def test_unprotected_gmail_session_or_unconfigured_ads_oauth_is_rejected():
    def invalid(path):
        code, body = healthy(path)
        if path == "/api/auth/session":
            return 200, '{"authenticated":true}'
        if path == "/api/public/ads-config":
            return 200, '{"google_client_id":"","meta_app_id":""}'
        return code, body
    issues = audit(invalid)
    assert len(issues) == 2


def test_staging_origin_must_be_https_and_on_owner_or_cloudflare_domain():
    assert validate_base_url("https://ads.lhmcrm.com/") == "https://ads.lhmcrm.com"
    assert validate_base_url("https://lhm-preview.workers.dev") == "https://lhm-preview.workers.dev"
    assert validate_base_url("https://lhm-preview.pages.dev/") == "https://lhm-preview.pages.dev"
    import pytest
    for bad in (
        "http://ads.lhmcrm.com", "https://localhost", "https://127.0.0.1",
        "https://evil.example", "https://ads.lhmcrm.com.evil.example",
        "https://ads.lhmcrm.com/other", "https://ads.lhmcrm.com?redirect=/",
        "https://user:pass@ads.lhmcrm.com", "https://ads.lhmcrm.com:444",
        "https://[broken", "https://ads.lhmcrm.com:abc",
    ):
        with pytest.raises(ValueError):
            validate_base_url(bad)


def test_staging_cli_json_reports_pass_without_real_network(monkeypatch, capsys):
    seen = []

    def fake_call(path, *, base):
        seen.append((path, base))
        return healthy(path)

    monkeypatch.setattr(smoke_gmail_production.smoke_production, "call", fake_call)
    assert main(["--base-url", "https://staging.lhmcrm.com", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["base_url"] == "https://staging.lhmcrm.com"
    assert report["status"] == "PASS"
    assert report["issues"] == []
    assert len(seen) == 4
    assert all(base == "https://staging.lhmcrm.com" for _path, base in seen)


def test_staging_cli_json_fails_closed_when_public_auth_not_ready(monkeypatch, capsys):
    def missing_auth(path, *, base):
        if path == "/api/auth/session":
            return 503, '{"code":"DEVICE_ONLY_NOT_READY"}'
        return healthy(path)

    monkeypatch.setattr(smoke_gmail_production.smoke_production, "call", missing_auth)
    assert main(["--base-url", "https://review.pages.dev", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FAIL"
    assert report["issues"] == ["Gmail session route missing or not correctly protected"]
