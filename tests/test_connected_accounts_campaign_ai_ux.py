"""Regression guards for customer-reported Google account import, campaigns and AI licensing UX."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return (ROOT/path).read_text(encoding='utf-8')


def test_oauth_pending_accounts_have_explicit_readable_dark_styles():
    css=read('static/connected-ux.css')
    html=read('static/studio.html')
    for fragment in (
        '#page-accounts .oauth-choice-box',
        'background:#1b1e24!important',
        'color:#f4f4f6!important',
        '#page-accounts .oauth-choice span',
        'color:#f0f1f4!important',
        '#page-accounts .oauth-choice input[type=checkbox]',
        '#page-accounts .oauth-choice:has(input:checked)',
        '@media(max-width:700px)'
    ):
        assert fragment in css
    assert '/static/connected-ux.css' in html
    assert html.index('/static/connected-ux.css')>html.index('/static/finpoint-theme.css')


def test_campaign_accounts_populate_on_any_route_with_timeout_and_retry():
    js=read('static/optimize.js')
    assert "new MutationObserver(()=>{if(onCampaignPage())populate()})" in js
    assert "document.addEventListener('lhm:accounts-loaded'" in js
    assert "new AbortController()" in js
    assert "setTimeout(()=>controller.abort(),15000)" in js
    assert "new Option('Không tải được tài khoản — thử lại','')" in js
    assert 'id="opt-retry"' in js
    assert 'data-go="accounts"' in js
    assert 'Chưa có tài khoản Ads đã lưu' in js
    assert "inspectButton.disabled=false" in js
    assert "node.style.color" not in js


def test_ai_license_error_is_explained_not_bypassed():
    ai=read('static/finpoint-accounts-ai.js')
    chat=read('static/studio.js')
    lic=read('ads_core/licensing.py')
    remote=read('ads_core/openrouter_ai.py')
    assert "api('/api/license')" in ai
    assert "Boolean(r.enabled&&!license.active)" in ai
    assert "window.lhmAILicenseBlocked=blocked" in ai
    assert "id='ai-license-warning'" in ai
    assert "go('license')" in ai
    assert "go('settings')" in ai
    assert "if(window.lhmAILicenseBlocked===true)" in chat
    assert "window.lhmRefreshAILicense?.()" in chat
    assert "license_required()" in remote
    assert "raise HTTPException(402" in lic
    assert 'id="ai-license-warning"' not in read('static/studio.html')


def test_prerender_campaign_and_license_styles_are_responsive():
    css=read('static/connected-ux.css')
    assert '#page-campaigns #opt-account option' in css
    assert '.campaign-state.error' in css
    assert '#page-assistant .ai-license-warning' in css
    assert '#page-assistant .ai-license-actions' in css
