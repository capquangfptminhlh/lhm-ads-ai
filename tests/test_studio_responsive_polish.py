"""Regression guards for responsive Studio dashboard UI."""
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "static" / "ui-polish.css").read_text(encoding="utf-8")


def test_compact_mobile_dashboard_and_touch_dock():
    assert "@media(max-width:360px)" in CSS
    assert "#shell .kpi-grid{grid-template-columns:minmax(0,1fr)}" in CSS
    assert "#shell .dashboard-grid{grid-template-columns:minmax(0,1fr)}" in CSS
    assert "env(safe-area-inset-left)" in CSS
    assert "env(safe-area-inset-right)" in CSS
    assert "-webkit-overflow-scrolling:touch" in CSS


def test_loading_feedback_and_reduced_motion():
    assert '.btn[aria-busy="true"]' in CSS
    assert "@keyframes ui-request-spin" in CSS
    assert "@media(prefers-reduced-motion:reduce)" in CSS
    assert '.btn[aria-busy="true"]::after{animation:none' in CSS


def test_no_visual_change_introduces_fake_report_data_or_api():
    new_section = CSS.split("/* Studio UX refinement:")[1]
    for forbidden in ("https://", "fetch(", "Math.random(", "localStorage"):
        assert forbidden not in new_section


def test_secondary_page_active_state_is_visible_on_mobile():
    script = (Path(__file__).resolve().parents[1] / "static" / "ui-polish.js").read_text(encoding="utf-8")
    assert "const onAdditionalPage = Boolean(selected)" in script
    assert "isOpen || onAdditionalPage" in script
    assert "more.setAttribute('aria-current', 'page')" in script
    assert "more.removeAttribute('aria-current')" in script
