"""Dashboard chart/table accessibility regression guards.

The alternate table must use exactly the data that feeds the API-backed chart.
"""
from pathlib import Path

S = Path(__file__).resolve().parents[1] / 'static'


def read(name):
    return (S / name).read_text(encoding='utf-8')


def test_chart_table_controls_are_accessible_and_disabled_until_report():
    html = read('studio.html')
    for name in ('chart-chart-toggle', 'chart-table-toggle', 'chart-data-view',
                 'chart-daily-body', 'chart-scroll-cue'):
        assert 'id="' + name + '"' in html
    assert 'aria-controls="chart-data-view"' in html
    assert 'aria-pressed="false" disabled' in html
    assert 'role="group" aria-label="Chế độ xem xu hướng chi tiêu"' in html
    assert 'role="region" aria-label="Dữ liệu chi tiêu theo ngày"' in html
    assert 'scope="col"' in html


def test_table_reuses_same_api_derived_entries_and_is_escaped_via_dom():
    js = read('studio.js')
    assert 'window.LHMFinpointChart(entries,selected)' in js
    assert 'renderDailyTable(entries,selected)' in js
    assert 'const rows=entries.map(([date,spend])=>' in js
    assert "day.textContent=date" in js
    assert "amount.textContent=fmt(spend)+' '+currency" in js
    assert "body.replaceChildren(...rows)" in js
    assert "document.createElement('th')" in js
    assert "document.createElement('td')" in js
    assert "$('chart-table-toggle').disabled=rows.length===0" in js
    assert "if(!rows.length)setChartView('chart')" in js


def test_toggle_and_reload_have_consistent_accessibility_state():
    js = read('studio.js')
    assert "setChartView('chart');" in js
    assert "$('chart-table-toggle').disabled=true" in js
    assert "$('chart').classList.toggle('hidden',tableMode)" in js
    assert "$('chart-data-view').classList.toggle('hidden',!tableMode)" in js
    assert "setAttribute('aria-pressed',String(tableMode))" in js
    assert "$('chart-chart-toggle').onclick=()=>setChartView('chart')" in js
    assert "$('chart-table-toggle').onclick=()=>setChartView('table')" in js
    assert "setAttribute('aria-busy','true')" in js
    assert "setAttribute('aria-busy','false')" in js


def test_mobile_visuals_and_reduced_motion():
    css = read('ui-polish.css')
    assert '#page-dashboard .chart-mode button' in css
    assert '#page-dashboard .chart-detail-scroll' in css
    assert '#page-dashboard .chart-data-view{animation:none}' in css
    assert '@media(max-width:650px)' in css
    assert 'animation:ui-chart-table-arrive' in css
