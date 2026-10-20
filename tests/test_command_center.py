"""Regression guards for FinPoint live local operations center."""
from pathlib import Path
STATIC=Path(__file__).resolve().parents[1]/'static'

def test_local_operations_wired_and_safe():
    html=(STATIC/'studio.html').read_text(encoding='utf-8')
    js=(STATIC/'finpoint-dashboard.js').read_text(encoding='utf-8')
    css=(STATIC/'finpoint-theme.css').read_text(encoding='utf-8')
    assert '/static/finpoint-dashboard.js' in html
    assert 'FinPoint v2: local monitoring' in js
    for endpoint in ('/api/monitor','/api/advisor/status','/api/license','/api/actions','/api/autopilot/plans'):
        assert endpoint in js
    assert '/api/autopilot/emergency-stop' in js
    assert "window.confirm(" in js and "me.role!=='admin'" in js
    assert "'X-CSRF-Token':me.csrf" in js
    assert 'textContent' in js and 'Math.random' not in js
    assert 'KHÔNG tắt chiến dịch' in js
    assert '@media(max-width:650px)' in css
