"""FinPoint AI/account interfaces use real local data and never submit AI automatically."""
from pathlib import Path

S = Path(__file__).resolve().parents[1] / "static"

def test_connected_finpoint_modules():
    html = (S / "studio.html").read_text(encoding="utf-8")
    js = (S / "finpoint-accounts-ai.js").read_text(encoding="utf-8")
    core = (S / "studio.js").read_text(encoding="utf-8")
    assert '/static/finpoint-accounts-ai.css' in html
    assert '/static/finpoint-accounts-ai.js' in html
    assert "new CustomEvent('lhm:accounts-loaded'" in core
    assert "document.addEventListener('lhm:accounts-loaded'" in js
    for tag in ('fp-accounts-google', 'fp-accounts-meta', 'fp-accounts-connected', 'fp-ai-mode', 'fp-ai-usage'):
        assert tag in js
    assert "isAdmin()" in js and "data-fp-campaign" in js
    assert "/api/ai/settings" in js
    assert "input.value=b.dataset.fpPrompt" in js
    assert "requestSubmit(" not in js and "Math.random" not in js
    assert "https://" not in js and "http://" not in js

def test_chart_is_dark_orange_and_no_invented_performance():
    css = (S / "finpoint-theme.css").read_text(encoding="utf-8")
    ai = (S / "finpoint-accounts-ai.js").read_text(encoding="utf-8")
    assert "background:linear-gradient(125deg,#202126" in css
    assert ".fp-chart .trendline{fill:none;stroke:#ff8a50" in css
    assert 'r.used_today' in ai
    assert 'Khi bấm Gửi' in ai
