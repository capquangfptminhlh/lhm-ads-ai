"""Motion integration checks: animation is progressive, local, and accessible."""
from pathlib import Path

S = Path(__file__).resolve().parents[1]/'static'


def test_finpoint_motion_loaded_without_external_assets():
    html=(S/'studio.html').read_text(encoding='utf-8')
    css=(S/'finpoint-motion.css').read_text(encoding='utf-8')
    js=(S/'finpoint-motion.js').read_text(encoding='utf-8')
    assert '/static/finpoint-motion.css' in html
    assert '/static/finpoint-motion.js' in html
    assert 'prefers-reduced-motion:reduce' in css
    assert '@keyframes fp-card-arrive' in css
    assert '@keyframes fp-line-reveal' in css
    assert '@keyframes fp-dot-in' in css
    assert 'sidebar-backdrop.open' in css
    assert "prefers-reduced-motion: reduce" in js
    assert "evt.key === 'Escape'" in js
    assert "evt.ctrlKey || evt.metaKey" in js
    assert "aria-current" in js
    assert "'lhm:dashboard-updated'" in js
    assert "window.cancelAnimationFrame" in js and "requestAnimationFrame" in js
    assert 'http://' not in js and 'https://' not in js
    assert "eval(" not in js and 'Math.random' not in js


def test_dashboard_kpi_animations_only_receive_true_api_totals():
    js=(S/'studio.js').read_text(encoding='utf-8')
    motion=(S/'finpoint-motion.js').read_text(encoding='utf-8')
    chart=(S/'finpoint-dashboard.js').read_text(encoding='utf-8')
    assert "new CustomEvent('lhm:dashboard-updated',{detail:{totals:t}})" in js
    assert "t.spend !== null" in motion
    assert "t.currency" in motion
    assert "k-impressions" in motion and "k-clicks" in motion and "k-ctr" in motion
    assert "data-motion-updated" in (S/'finpoint-motion.css').read_text(encoding='utf-8')
    assert "style=\"--fp-point:${i}\"" in chart
