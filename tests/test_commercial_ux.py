"""Lock the commercial-clarity upgrade of the License panel (2026-10-21).

The panel (static/commercial.js) now renders a dedicated license status
box with three states computed only from the /api/license payload, plus a
3-step activation checklist for first-run users. All styling is via CSS
classes in static/workspace-pages.css because the app CSP (style-src
'self') silently drops inline styles.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "static"

JS = (S / "commercial.js").read_text(encoding="utf-8")
CSS = (S / "workspace-pages.css").read_text(encoding="utf-8")


def test_no_inline_styles_in_commercial_js():
    assert 'style="' not in JS
    assert "style='" not in JS
    assert ".style." not in JS  # no element.style assignments either


def test_status_box_uses_payload_fields_only():
    assert 'id="license-status-box"' in JS
    assert 'id="license-status-line"' in JS
    assert 'id="license-status-guidance"' in JS
    assert "function renderLicenseStatus(license)" in JS
    assert "license.active" in JS
    assert "license.plan" in JS
    assert "license.expires_at" in JS
    assert "license.reason" in JS


def test_three_states_exist_with_css_flag_classes():
    # The box class is composed as 'license-status-' + state in the JS.
    assert "license-status-'+state" in JS
    for state, cls in (("active", "license-status-active"),
                       ("expiring", "license-status-expiring"),
                       ("inactive", "license-status-inactive")):
        assert f"state='{state}'" in JS, state
        assert "." + cls in CSS, cls


def test_active_state_always_shows_days_remaining():
    # Days remaining must render for every active license, not only <=7.
    assert "Còn ${days} ngày" in JS
    assert "Bản quyền đang hoạt động" in JS
    assert "days>7" in JS  # the >7 branch is the always-on display


def test_expiring_state_has_renewal_guidance():
    assert "Bản quyền sắp hết hạn" in JS
    assert ("Gia hạn: gửi mã máy cho đơn vị cung cấp và chuyển khoản "
            "theo hướng dẫn đã nhận") in JS


def test_inactive_state_explains_read_only():
    assert "Chưa kích hoạt hoặc giấy phép đã hết hạn" in JS
    assert "Chế độ chỉ đọc" in JS
    assert "vẫn có thể xem và xuất báo cáo" in JS
    assert "đang tạm dừng cho đến khi kích hoạt lại" in JS


def test_clock_reason_messages_kept_intact():
    assert ("Đồng hồ Windows bị chỉnh lùi. Vui lòng đồng bộ giờ chính xác "
            "để tiếp tục sử dụng.") in JS
    assert ("Dữ liệu kiểm tra thời gian bị lỗi. Liên hệ hỗ trợ, "
            "không xóa dữ liệu ứng dụng.") in JS


def test_activation_checklist_three_steps():
    assert 'id="license-activate-steps"' in JS
    assert "Làm theo 3 bước để kích hoạt" in JS
    assert "Sao chép mã máy" in JS                       # step 1
    assert "Gửi mã máy cho đơn vị cung cấp và chuyển khoản" in JS  # step 2
    assert "license.json" in JS and "Kích hoạt / Gia hạn" in JS    # step 3
    # The checklist is only for users without an active license.
    assert "steps.classList.toggle('hidden',!!license.active)" in JS


def test_status_css_classes_defined():
    for cls in ("license-status", "license-status-line",
                "license-status-guidance", "license-status-unknown",
                "license-steps", "license-steps-list"):
        assert "." + cls in CSS, cls


def test_show_message_classes_stay_compatible():
    # show() must keep using the class pair the defect-fix round defined.
    assert "commercial-error" in JS and "commercial-ok" in JS
    assert "#commercial-message.commercial-ok" in CSS
    assert "#commercial-message.commercial-error" in CSS
