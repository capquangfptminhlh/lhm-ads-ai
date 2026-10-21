"""Lock the 2026-10-21 visual-review fixes.

The Studio app serves a strict CSP (style-src 'self') that silently drops
inline style attributes emitted by its own JavaScript, which had mangled
the License page layout. These tests keep inline styles out of the static
assets and pin the other five reviewed defects.
"""
from pathlib import Path

S = Path(__file__).resolve().parents[1] / "static"


def _read(name):
    return (S / name).read_text(encoding="utf-8")


def test_no_inline_style_attributes_in_js_or_html():
    for name in ("commercial.js", "optimize.js", "advisor.js", "autopilot.js",
                 "finpoint-dashboard.js", "goal-settings.js", "permissions.js",
                 "provider-studio.js", "workspace-pages.js",
                 "finpoint-accounts-ai.js", "finpoint-operations.js",
                 "studio.js", "studio.html", "commercial.js"):
        text = _read(name)
        assert 'style="' not in text, f"{name} still emits an inline style attribute"
        assert "style='" not in text, f"{name} still emits an inline style attribute"


def test_setup_strength_meter_uses_classes_not_inline_styles():
    js = _read("setup.js")
    assert "fill.style" not in js
    assert "lvl-high" in js
    css = _read("setup.css")
    for cls in (".w1", ".w2", ".w3", ".w4", ".w5", ".lvl-low", ".lvl-mid", ".lvl-high"):
        assert cls in css


def test_commercial_message_uses_css_classes_and_clears_on_success():
    js = _read("commercial.js")
    assert "p.style.color" not in js
    assert "commercial-error" in js and "commercial-ok" in js
    # A stale pre-login error must not survive a successful refresh, and the
    # pre-login refresh must not print auth errors at all.
    assert "classList.contains('hidden')" in js
    assert "msg.textContent=''" in js
    css = _read("workspace-pages.css")
    assert ".commercial-ok" in css and ".commercial-error" in css
    assert ".wrap-anywhere" in css and ".btn-row" in css


def test_ai_consent_checkbox_stays_attached_to_its_label():
    css = _read("workspace-pages.css")
    assert ".ai-consent{display:flex" in css
    assert ".ai-consent input{width:auto" in css


def test_campaigns_account_picker_has_empty_state():
    js = _read("optimize.js")
    assert "Chưa có tài khoản đã kết nối" in js
    assert "opt-inspect').disabled" in js
    assert "Đang tải tài khoản…" in js


def test_dashboard_chips_no_longer_duplicate_each_other():
    js = _read("finpoint-dashboard.js")
    assert "Nguồn: chưa kết nối tài khoản" in js
    assert "'Chưa có dữ liệu thực'" not in js


def test_theme_leftovers_removed():
    theme = _read("finpoint-theme.css")
    assert "radial-gradient(circle,#ff613020" not in theme  # KPI corner smudge
    assert ".login-mobile-logo{color:var(--fp-orange)}" in theme
