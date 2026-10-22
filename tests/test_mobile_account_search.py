"""Account search is usable on mobile and stays accurate across provider filters."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
S=ROOT/'static'


def test_mobile_search_field_and_result_feedback_are_accessible():
    html=(S/'studio.html').read_text(encoding='utf-8')
    css=(S/'ui-polish.css').read_text(encoding='utf-8')
    for anchor in ('id="account-list-search"','id="account-search-status"',
                   'id="account-filter-empty"','aria-live="polite"',
                   'aria-describedby="account-search-status"'):
        assert anchor in html
    assert '#page-accounts #account-list-search' in css
    assert 'font-size:16px' in css
    assert '@media(max-width:650px)' in css


def test_debounced_api_not_used_for_filter_and_search_is_accent_insensitive():
    js=(S/'studio.js').read_text(encoding='utf-8')
    assert 'function applyAccountSearch()' in js
    assert 'function syncAccountSearch(value,source)' in js
    assert 'function normalizeAccountSearch(value)' in js
    assert "normalize('NFD')" in js
    assert 'document.querySelectorAll(\'#accounts-table tbody tr[data-platform]\')' in js
    assert "'account-search-status'" in js
    assert "'account-filter-empty'" in js
    assert "'global-account-search','account-list-search'" in js


def test_keyboard_search_chooses_visible_field_on_small_screens():
    motion=(S/'finpoint-motion.js').read_text(encoding='utf-8')
    assert "window.matchMedia('(max-width: 650px)').matches" in motion
    assert "mobile ? $('account-list-search') : $('global-account-search')" in motion
    smoke=(ROOT/'tools/ui-smoke.py').read_text(encoding='utf-8')
    assert '15-mobile-accounts-search.png' in smoke
    assert "page.keyboard.press('Control+k')" in smoke
    assert "expect(page.locator('#account-list-search')).to_be_focused()" in smoke
