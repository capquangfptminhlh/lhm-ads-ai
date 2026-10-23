"""Navigation and license UX stay simple without disabling features or misrepresenting verification."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
S=ROOT/'static'
def read(name):return (S/name).read_text(encoding='utf-8')


def test_inter_is_bundled_and_global_typography_is_consistent():
    html=read('studio.html')
    css=read('studio-simple.css')
    assert '/static/fonts.css' in html
    assert '/static/studio-simple.css' in html
    assert html.index('/static/studio-simple.css')>html.index('/static/finpoint-theme.css')
    assert 'font-family:Inter,"Segoe UI",system-ui,sans-serif' in css
    assert 'font-synthesis:none' in css
    assert 'line-height:1.58' in css
    assert 'font-size:14px' in css
    assert 'font-size:clamp(26px,2.35vw,32px)' in css


def test_nav_advances_reveal_all_tools_without_deleting_routes():
    html=read('studio.html')
    js=read('studio.js')
    assert '<details id="nav-advanced"' in html
    assert '<summary aria-label="Mở hoặc thu gọn chức năng nâng cao">' in html
    opening=html.index('<details id="nav-advanced"')
    closing=html.index('</details>',opening)
    advanced=html[opening:closing]
    for route in ('autopilot','alerts','reports','approvals','team','audit','settings'):
        assert 'data-page="'+route+'"' in advanced
    for route in ('dashboard','accounts','campaigns','assistant','license'):
        assert html.index('data-page="'+route+'"')<opening
    assert "advanced.open=true" in js
    assert "'reports','approvals','team','audit','settings'" in js
    assert '#shell #navigation .nav-advanced>summary' in read('studio-simple.css')


def test_license_has_live_summary_and_collapsible_technical_controls():
    js=read('commercial.js')
    for ident in ('license-overview-state','license-overview-device',
                  'license-overview-provider','license-overview-data',
                  'license-activation-panel','license-monitor-panel',
                  'license-readiness-detail','license-backup-detail',
                  'readiness-checks','secure-backup-export',
                  'monitor-save','license-activate'):
        assert ident in js
    assert "activation.open=!license.active" in js
    assert 'new MutationObserver(' in js
    assert "watcher.observe(target,{attributes:true,attributeFilter:['class']})" in js
    assert "data.ready_for_commercial_distribution?" in js
    assert "api('/api/desktop/readiness')" in js
    assert "api('/api/desktop/backup/export'" not in js  # backup uses fetch for Blob


def test_statuses_are_vietnamese_and_not_falsely_verified():
    js=read('commercial.js')
    for word in ('Dữ liệu SQLite trên máy',
                 'Giấy phép thuê bao theo máy',
                 'Ứng dụng Google OAuth · chưa xác minh quyền Ads',
                 'Kết nối API quảng cáo thật',
                 'Chữ ký nhà phát hành file EXE',
                 'CHƯA XÁC MINH',
                 'Bản quyền và thiết bị',
                 'Kết nối quảng cáo',
                 'Dữ liệu và vận hành'):
        assert word in js
    assert "apiCheck?.status==='ok'?'API đã xác minh':'API chưa xác minh'" in js
    assert "new Map(data.checks.map(x=>[x.code,x]))" in js
    assert 'escape(descriptions[code]||item.detail)' in js


def test_mobile_and_a11y_contrast_are_not_a_horizontal_scroll_hack():
    css=read('studio-simple.css')
    for rule in ('@media(max-width:720px)','@media(max-width:380px)',
                 '@media(prefers-reduced-motion:reduce)',
                 '#page-license .license-check-row',
                 '#page-license .license-state-pill',
                 '#page-license .license-disclosure>summary'):
        assert rule in css
    assert 'overflow-x:hidden' not in css
    assert 'display:none!important' not in css
