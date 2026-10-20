"""Regression tests for separate Google and Meta provider selection."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def read(name): return (ROOT/name).read_text(encoding='utf-8')

def test_provider_choice_and_guidance():
    h=read('static/studio.html')
    for p in ('google','meta'):
        assert f'data-provider-choice="{p}"' in h
        assert f'data-provider-detail="{p}"' in h
        assert f'id="oauth-{p}"' in h
        assert f'id="desktop-{p}-form"' in h
        assert f'data-provider-settings="{p}"' in h
        assert f'data-manual-platform="{p}"' in h
    assert 'https://console.cloud.google.com/apis/credentials' in h
    assert 'https://developers.facebook.com/apps/' in h
    assert '<select id="acc-platform"' not in h
    assert 'id="acc-platform" name="platform" value="demo"' in h

def test_account_filter_is_provider_specific():
    h=read('static/studio.html')
    s=read('static/studio.js')
    w=read('static/provider-studio.js')
    for p in ('all','google','meta','demo'):
        assert f'data-account-filter="{p}"' in h
        assert f'id="account-count-{p}"' in h
    assert "window.lhmAccountFilter||'all'" in s
    assert 'data-platform=' in s
    assert 'window.lhmProviderUI?.renderCounts?.(cache)' in s
    assert 'tr.dataset.platform!==platform' in s
    assert "api('/api/report?account_id='" in w
    assert "window.lhmSelectedProvider = provider;" in w
    assert "box.dataset.pendingProvider=flow.provider" in s

def test_reduced_motion_keyboard_and_assets():
    h=read('static/studio.html')
    css=read('static/provider-studio.css')
    js=read('static/provider-studio.js')
    assert '/static/provider-studio.css' in h and '/static/provider-studio.js' in h
    assert 'aria-label="Chọn nền tảng quảng cáo"' in h
    assert 'ArrowLeft' in js and 'ArrowRight' in js
    assert '@keyframes studio-page-enter' in css
    assert '@keyframes studio-grow-bar' in css
    assert '@media(prefers-reduced-motion:reduce)' in css

def test_no_oauth_password_or_mcp_on_connect_ui():
    h=read('static/studio.html')
    js=read('static/provider-studio.js')
    assert 'Không yêu cầu mật khẩu Google' in h
    assert 'Không nhập mật khẩu Facebook' in h
    assert 'Kết nối MCP' not in h
    assert 'META_APP_SECRET=' not in js
