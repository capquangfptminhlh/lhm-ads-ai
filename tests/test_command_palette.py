"""Command palette only navigates within the existing permission-aware Studio UI."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'static'
def read(file):
    return (ROOT/file).read_text(encoding='utf-8')


def test_command_palette_is_bundled_and_accessible():
    html=read('studio.html')
    css=read('command-palette.css')
    assert '/static/command-palette.css' in html
    assert '/static/command-palette.js' in html
    assert 'id="ui-command-open"' in html
    assert 'id="ui-command-overlay"' in html
    assert 'role="dialog" aria-modal="true"' in html
    assert 'id="ui-command-input"' in html
    assert 'role="combobox"' in html
    assert 'id="ui-command-results"' in html
    assert 'role="listbox"' in html
    assert '@media(max-width:700px)' in css
    assert 'env(safe-area-inset-bottom)' in css
    assert 'prefers-reduced-motion:reduce' in css


def test_command_palette_is_safe_read_only_and_permission_aware():
    script=read('command-palette.js')
    assert "link.closest('.hidden')" in script
    assert "link.classList.contains('hidden')" in script
    assert 'item.link.click()' in script
    assert "new MutationObserver" in script
    assert "evt.key === 'Escape'" in script
    assert "evt.key === 'ArrowDown'" in script
    assert "evt.key === 'ArrowUp'" in script
    assert "evt.key === 'Enter'" in script
    assert "evt.key === 'Tab'" in script
    assert "role','option'" in script
    assert 'aria-activedescendant' in script
    assert 'normalize(' in script
    for forbidden in ('fetch(', 'XMLHttpRequest', 'document.cookie', 'localStorage',
                      'sessionStorage', 'eval(', 'https://', "api('/api/actions"):
        assert forbidden not in script
    assert 'style="' not in read('studio.html')


def test_old_account_shortcut_remains_unchanged():
    old=read('finpoint-motion.js')
    assert "evt.ctrlKey || evt.metaKey" in old
    assert "evt.key.toLowerCase() === 'k'" in old
    palette=read('command-palette.js')
    assert "evt.key.toLocaleLowerCase('en') === 'p'" in palette
