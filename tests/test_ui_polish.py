"""UI polish regression guards; actual navigation is also exercised by Playwright."""
from pathlib import Path

S = Path(__file__).resolve().parents[1] / 'static'


def read(name):
    return (S / name).read_text(encoding='utf-8')


def test_onboarding_only_for_no_connected_real_provider():
    html=read('studio.html')
    app=read('studio.js')
    assert 'id="dashboard-onboarding"' in html
    assert 'data-go="accounts"' in html
    assert 'id="ui-onboarding-title"' in html
    assert "['google','meta'].includes(a.platform)&&a.connected" in app
    assert "!String(a.label||'').startsWith('[REVOKED]')" in app
    assert "$('dashboard-onboarding')?.classList.toggle('hidden',liveAccounts.length>0)" in app
    assert "$('dashboard-onboarding')?.classList.add('hidden')" in app


def test_mobile_nav_reuses_original_sidebar_escape_and_selected_page():
    html=read('studio.html')
    script=read('ui-polish.js')
    theme=read('ui-polish.css')
    assert 'class="ui-mobile-dock"' in html
    for page in ('dashboard','accounts','reports','assistant'):
        assert 'data-ui-tab="'+page+'"' in html
    assert 'id="ui-dock-more"' in html
    assert 'menu.click()' in script
    assert "setAttribute('aria-current', 'page')" in script
    assert 'aria-expanded' in script
    assert 'window.scrollTo(0, 0)' in script
    assert '.sidebar-backdrop' in theme
    assert 'env(safe-area-inset-bottom)' in theme
    assert '@media(max-width:900px)' in theme
    assert '@media(max-width:650px)' in theme


def test_polish_css_last_and_reduced_motion():
    html=read('studio.html')
    css=read('ui-polish.css')
    script=read('ui-polish.js')
    assert html.index('/static/finpoint-motion.css') < html.index('/static/ui-polish.css')
    assert html.index('/static/finpoint-motion.js') < html.index('/static/ui-polish.js')
    assert 'prefers-reduced-motion:reduce' in css
    assert 'var(--ui-focus)' in css
    assert 'position:sticky' in css
    for source in (html,script):
        assert 'style="' not in source
        assert "style='" not in source
    for token in ('fetch(', 'XMLHttpRequest', 'https://', 'Math.random(', 'eval('):
        assert token not in script
