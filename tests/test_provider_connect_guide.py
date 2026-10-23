"""Guided local provider onboarding without exposing credentials to third-party AI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(path): return (ROOT / path).read_text(encoding='utf-8')


def test_wizard_is_exposed_in_settings_and_works_on_mobile():
    html=read('static/studio.html')
    css=read('static/connection-guide.css')
    assert 'id="provider-connect-guide"' in html
    assert 'id="connection-guide-body"' in html
    assert 'id="connection-guide-status" role="status" aria-live="polite"' in html
    assert 'data-connect-provider="google"' in html
    assert 'data-connect-provider="meta"' in html
    for i in range(4):
        assert f'data-connect-step="{i}"' in html
    assert '/static/connection-guide.js' in html
    assert '/static/connection-guide.css' in html
    assert '@media(max-width:650px)' in css
    assert '@media(prefers-reduced-motion:reduce)' in css
    assert ':focus-visible' in css


def test_json_import_is_local_only_and_must_not_auto_submit():
    script=read('static/connection-guide.js')
    assert "const item=contents?.installed" in script
    assert "file.size > 128*1024" in script
    assert "byId('desktop-google-id').value=item.client_id" in script
    assert "byId('desktop-google-secret').value=item.client_secret || ''" in script
    assert 'Đã điền Client ID và Secret từ file, chưa lưu' in script
    assert "if(button.id==='connection-save'){performSave();return;}" in script
    assert "navigator.clipboard?.writeText" in script
    for forbidden in ('fetch(', 'XMLHttpRequest', 'openai.com', 'api.openrouter', 'eval(', 'localStorage.setItem'):
        assert forbidden not in script


def test_guidance_lists_platform_prerequisites_without_promising_bypass():
    script=read('static/connection-guide.js')
    for phrase in ('Desktop app', 'Google Ads API', 'developer token',
                   'App Review', 'ads_read', 'Redirect URI', 'HTTPS'):
        assert phrase in script
    assert "readiness[p] = data[p]?.configured===true" in script
    assert 'Chủ tài khoản' in read('static/studio.html')
    assert "window.lhmProviderUI?.setProvider?.(provider)" in script


def test_source_only_emits_safe_provider_status():
    script=read('static/studio.js')
    assert "new CustomEvent('lhm:desktop-providers-status'" in script
    fragment=script.split("new CustomEvent('lhm:desktop-providers-status'")[1].split('}));')[0]
    assert 'callback_url' in fragment and 'configured' in fragment
    assert 'client_secret' not in fragment and 'client_id' not in fragment


def test_accounts_routes_to_wizard_instead_of_secret_form():
    script=read('static/provider-studio.js')
    assert "new CustomEvent('lhm:open-connect-guide'" in script
    assert "detail:{provider:btn.dataset.providerSettings}" in script



def test_api_and_mcp_are_explicitly_separate_guidance_modes():
    html=read('static/studio.html')
    js=read('static/connection-guide.js')
    css=read('static/connection-guide.css')
    guide=read('docs/ADS_CONNECT_API_MCP_GUIDE.md')
    assert 'data-connection-mode="api"' in html
    assert 'data-connection-mode="mcp"' in html
    assert 'MCP là kết nối riêng' in html
    assert 'let mode = \'api\'' in js
    assert "mode==='mcp'?mcpGuides[provider]:templates[provider][step]" in js
    assert "root.querySelector('.connection-step-nav').classList.toggle('hidden',mode==='mcp')" in js
    assert '#provider-connect-guide .connection-mode-switch' in css
    assert 'MCP Google Ads' in guide and 'MCP Meta Ads' in guide
    assert 'chưa được tích hợp' in guide


def test_current_google_ads_cloud_access_rules_not_outdated():
    js=read('static/connection-guide.js')
    guide=read('docs/ADS_CONNECT_API_MCP_GUIDE.md')
    assert '09/09/2026' in js
    assert 'Explorer' in js and 'Google Cloud' in js
    assert '09/09/2026' in guide
    assert 'developer token Google Ads API đã sunset' in guide
    assert 'ads_read' in guide and 'ads_management' in guide
    assert 'https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server' in js
    assert 'https://developers.facebook.com/ads-mcp-server' in js
