"""Native OAuth browser callback page: accessible, safe and clear to exit."""
import base64
import re
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
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8765")


def test_success_screen_explains_import_is_still_required(monkeypatch, tmp_path):
    _configure_desktop(monkeypatch, tmp_path)
    with TestClient(app, client=("127.0.0.1", 52739)) as browser:
        page = browser.get("/oauth/finished?status=ready")
        assert page.status_code == 200
        assert "Đã nhận quyền truy cập" in page.text
        assert "chọn tài khoản quảng cáo" in page.text
        assert "Lưu tài khoản đã chọn" in page.text
        assert "Quay lại LHM Ads AI" in page.text
        assert "data-return-token=" in page.text
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


def test_return_action_uses_one_time_token_and_safe_origin(monkeypatch, tmp_path):
    _configure_desktop(monkeypatch, tmp_path)
    from windows import desktop_window
    attempts = []
    monkeypatch.setattr(desktop_window, "focus_native_window",
                        lambda: attempts.append("focus") or True)
    with TestClient(app, client=("127.0.0.1", 52739)) as browser:
        page = browser.get("/oauth/finished?status=ready")
        token = re.search(r'data-return-token="([^"]+)"', page.text).group(1)
        endpoint = "/api/oauth/finished/activate"
        headers = {"origin": "http://127.0.0.1:8765",
                   "content-type": "application/json",
                   "sec-fetch-site": "same-origin",
                   "x-lhm-return-token": token}
        assert browser.post(endpoint, headers={**headers, "origin": "https://evil.invalid"},
                            json={}).status_code == 403
        assert browser.post(endpoint, headers={**headers, "content-type": "text/plain"},
                            content="{}").status_code == 403
        assert browser.post(endpoint, headers={**headers, "sec-fetch-site": "cross-site"},
                            json={}).status_code == 403
        result = browser.post(endpoint, headers=headers, json={})
        assert result.status_code == 200
        assert result.json() == {"activated": True}
        assert attempts == ["focus"]
        assert browser.post(endpoint, headers=headers, json={}).status_code == 403
        assert browser.post(endpoint, headers={**headers, "x-lhm-return-token": "invalid"},
                            json={}).status_code == 403


def test_no_remote_focusing_and_no_lingering_token(monkeypatch, tmp_path):
    _configure_desktop(monkeypatch, tmp_path)
    from ads_core import oauth_connect
    with TestClient(app, client=("127.0.0.1", 52739)) as browser:
        page=browser.get("/oauth/finished")
        token=re.search(r'data-return-token="([^"]+)"', page.text).group(1)
        # Expire only the in-memory nonce, not the process-wide time module.
        with oauth_connect._desktop_return_lock:
            oauth_connect._desktop_return_tokens[token] = 0
    with TestClient(app, client=("127.0.0.1", 52739)) as browser:
        r=browser.post("/api/oauth/finished/activate",
                       headers={"origin": "http://127.0.0.1:8765",
                                "content-type": "application/json",
                                "x-lhm-return-token": token}, json={})
        assert r.status_code == 403
    with TestClient(app, client=("198.51.100.2", 52739)) as browser:
        assert browser.post("/api/oauth/finished/activate", json={}).status_code == 404


def test_return_to_app_ux_and_visibility_do_not_expose_provider_tokens():
    css = (ROOT / "static" / "oauth-finished.css").read_text(encoding="utf-8")
    js = (ROOT / "static" / "oauth-finished.js").read_text(encoding="utf-8")
    assert "background:#0b0e13;color:#f5f6f8" in css
    assert "color:#fff" in css
    assert "min-height:100dvh" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "window.close()" not in js
    assert "api/oauth/finished/activate" in js
    assert "credentials: 'omit'" in js
    assert "Alt + Tab" in js
    assert "Ctrl + W" in js
    for forbidden in ("localStorage", "oauth_token", "refresh_token", "XMLHttpRequest"):
        assert forbidden not in js


def test_native_webview_return_is_temporary_and_never_kills_browser(monkeypatch):
    import windows.desktop_window as desktop
    class FakeTimer:
        def __init__(self, duration, callback): self.callback=callback; self.daemon=False
        def start(self): pass
        def cancel(self): pass
    class Window:
        def __init__(self): self.on_top=False; self.shown=False
        def show(self): self.shown=True
    w=Window()
    monkeypatch.setattr(desktop, "_native_window", w)
    monkeypatch.setattr(desktop.threading, "Timer", FakeTimer)
    assert desktop.focus_native_window() is True
    assert w.on_top is True and w.shown is True
    timer=desktop._focus_reset_timer
    timer.callback()
    assert w.on_top is False
    monkeypatch.setattr(desktop, "_native_window", None)
    assert desktop.focus_native_window() is False
