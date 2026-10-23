"""Native OAuth browser callback page: accessible, safe and clear to exit."""
import base64
from pathlib import Path

from fastapi.testclient import TestClient
from ads_core.extended import app

ROOT = Path(__file__).resolve().parents[1]


def _configure_desktop(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "oauth-finished.sqlite"))
    monkeypatch.setenv("MASTER_KEY", base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("SESSION_SECRET", "oauth-finished-test-session-secret-minimum-32")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("LHM_DESKTOP_MODE", "1")


def test_success_screen_explains_import_is_still_required(monkeypatch, tmp_path):
    _configure_desktop(monkeypatch, tmp_path)
    with TestClient(app, client=("127.0.0.1", 52739)) as browser:
        page = browser.get("/oauth/finished?status=ready")
        assert page.status_code == 200
        assert "Đã nhận quyền truy cập" in page.text
        assert "chọn tài khoản quảng cáo" in page.text
        assert "Lưu tài khoản đã chọn" in page.text
        assert "Đóng tab &amp; quay lại phần mềm" in page.text
        assert "<kbd>Ctrl</kbd> + <kbd>W</kbd>" in page.text
        assert '/static/oauth-finished.css' in page.text
        assert '/static/oauth-finished.js' in page.text
        assert page.headers["cache-control"] == "no-store"
        assert "script-src 'self'" in page.headers["content-security-policy"]
        assert browser.get("/static/oauth-finished.css").status_code == 200
        assert browser.get("/static/oauth-finished.js").status_code == 200


def test_failure_states_are_explicit_and_query_not_reflected(monkeypatch, tmp_path):
    _configure_desktop(monkeypatch, tmp_path)
    expected = {
        "cancelled": "Bạn đã hủy cấp quyền",
        "no_accounts": "Chưa tìm thấy tài khoản Ads",
        "provider_error": "Chưa lấy được dữ liệu quảng cáo",
        "error": "Không thể hoàn thành kết nối",
    }
    with TestClient(app, client=("127.0.0.1", 52739)) as browser:
        for state, label in expected.items():
            page = browser.get("/oauth/finished", params={"status": state})
            assert page.status_code == 200
            assert label in page.text
            assert 'class="oauth-finished warning"' in page.text
        arbitrary = browser.get("/oauth/finished", params={"status": "<script>alert(1)</script>"})
        assert arbitrary.status_code == 200
        assert "<script>alert(1)</script>" not in arbitrary.text
        assert "Không thể hoàn thành kết nối" in arbitrary.text


def test_finished_page_is_loopback_desktop_only(monkeypatch, tmp_path):
    _configure_desktop(monkeypatch, tmp_path)
    with TestClient(app, client=("198.51.100.3", 1234)) as other_host:
        assert other_host.get("/oauth/finished").status_code == 404
    monkeypatch.setenv("LHM_DESKTOP_MODE", "0")
    with TestClient(app, client=("127.0.0.1", 1234)) as web_mode:
        assert web_mode.get("/oauth/finished").status_code == 404


def test_close_fallback_and_visibility_do_not_depend_on_provider_tokens():
    css = (ROOT / "static" / "oauth-finished.css").read_text(encoding="utf-8")
    js = (ROOT / "static" / "oauth-finished.js").read_text(encoding="utf-8")
    assert "background:#0b0e13;color:#f5f6f8" in css
    assert "color:#fff" in css
    assert "min-height:100dvh" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "window.close()" in js
    assert "window.closed" in js
    assert "Ctrl" in js and "W" in js
    for forbidden in ("fetch(", "localStorage", "oauth_token", "refresh_token", "XMLHttpRequest"):
        assert forbidden not in js
