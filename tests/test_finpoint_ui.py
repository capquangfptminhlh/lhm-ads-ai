"""Static guards for the dark FinPoint-inspired UI. Metrics remain API-backed."""
from pathlib import Path
STATIC=Path(__file__).resolve().parents[1]/'static'

def test_finpoint_loaded_and_uses_real_report_data():
    h=(STATIC/'studio.html').read_text(encoding='utf-8')
    js=(STATIC/'studio.js').read_text(encoding='utf-8')
    chart=(STATIC/'finpoint-dashboard.js').read_text(encoding='utf-8')
    assert '/static/finpoint-theme.css' in h
    assert '/static/finpoint-dashboard.js' in h
    assert h.index('finpoint-dashboard.js')<h.index('studio.js')
    assert 'fp-ops-connected' in h and 'fp-ops-failed' in h
    assert 'window.LHMFinpointChart(entries,selected)' in js
    assert 'window.LHMFinpointSummary?.(t,accounts,s)' in js
    assert 'entries.map(e=>Number(e[1]))' in chart
    assert 'fetch(' not in chart and 'XMLHttpRequest' not in chart
    assert 'Math.random' not in chart

def test_dark_theme_responsive_a11y():
    css=(STATIC/'finpoint-theme.css').read_text(encoding='utf-8')
    chart=(STATIC/'finpoint-dashboard.js').read_text(encoding='utf-8')
    for required in ('prefers-reduced-motion:reduce','@media(max-width:610px)', '.fp-ops', '.chart-panel', '.icon-btn.mobile'):
        assert required in css
    assert 'role="img"' in chart
    assert 'aria-label=' in chart

def test_dashboard_explicit_status_and_demo_isolation_markers():
    h=(STATIC/'studio.html').read_text(encoding='utf-8')
    js=(STATIC/'studio.js').read_text(encoding='utf-8')
    css=(STATIC/'finpoint-theme.css').read_text(encoding='utf-8')
    for element in ('dashboard-data-status','dashboard-currency','conversion-strip','k-conversions','k-cpa','k-roas'):
        assert 'id="'+element+'"' in h
    assert "r.source==='demo'" in js
    assert "t.data_mode==='demo'" in js
    assert "'lhm:dashboard-reset'" in js
    assert 'overscroll-behavior-x:contain' in css
