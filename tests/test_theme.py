"""Lightweight guardrails for the warm studio theme."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_warm_theme_loaded_and_mobile_breakpoints():
    html = (ROOT / 'static/studio.html').read_text(encoding='utf-8')
    theme = (ROOT / 'static/reference-theme.css').read_text(encoding='utf-8')
    assert '/static/reference-theme.css' in html
    assert '.sidebar{' in theme
    assert '--canvas:#f2e7df' in theme
    assert '@media(max-width:610px)' in theme

def test_user_navigation_not_promoting_mcp():
    html = (ROOT / 'static/studio.html').read_text(encoding='utf-8')
    assert 'Kết nối MCP' not in html
    assert 'id="global-account-search"' in html
    assert 'class="sidebar-create"' in html

def test_search_is_connected_to_real_accounts_table():
    js = (ROOT / 'static/studio.js').read_text(encoding='utf-8')
    assert 'function applyAccountSearch()' in js
    assert "$('global-account-search')" in js
    assert "#accounts-table tbody tr" in js
