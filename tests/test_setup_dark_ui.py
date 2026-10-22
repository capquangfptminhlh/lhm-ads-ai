"""Prevent the shipped first-run UI drifting from the actual dark Studio again."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'static'


def test_first_run_skin_is_loaded_after_legacy_styles():
    html=(STATIC/'setup.html').read_text(encoding='utf-8')
    dark=(STATIC/'setup-dark.css').read_text(encoding='utf-8')
    assert html.index('/static/setup.css') < html.index('/static/setup-dark.css')
    assert '<meta name="theme-color" content="#0b0c0e">' in html
    assert 'Dashboard đen' in html
    assert 'XEM TRƯỚC BỐ CỤC · CHƯA CÓ DỮ LIỆU ADS' in html
    assert '--setup-bg:#0b0c0e' in dark
    assert '--setup-surface:#17181c' in dark
    assert 'color-scheme:dark' in dark
    assert '@media(max-width:660px)' in dark
    assert 'prefers-reduced-motion:reduce' in dark


def test_first_run_copy_does_not_pretend_local_http_is_https():
    html=(STATIC/'setup.html').read_text(encoding='utf-8')
    assert '✓ Kết nối HTTPS' not in html
    assert '✓ Chạy trên máy cá nhân' in html


def test_real_exe_assets_and_chromium_first_run_are_ci_gated():
    windows=(ROOT/'windows/smoke-test.ps1').read_text(encoding='utf-8')
    ci=(ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert '/static/setup-dark.css' in windows
    assert 'First-run screen does not match dark Studio theme' in windows
    assert 'python tools/setup_ui_smoke.py' in ci
    assert 'Test actual first-run setup on desktop/mobile' in ci
