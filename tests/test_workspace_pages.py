"""FinPoint dedicated workspace modules retain the underlying secure workflows."""
from pathlib import Path
S=Path(__file__).resolve().parents[1]/'static'
def test_all_tabs_are_real_and_no_duplicate_ids():
    h=(S/'studio.html').read_text(encoding='utf-8')
    import re
    ids=re.findall(r'\bid="([^"]+)"',h)
    assert len(ids)==len(set(ids)), 'Duplicate HTML IDs'
    for name in ('campaigns','autopilot','alerts','reports','license'):
        assert 'data-page="'+name+'"' in h
        assert 'id="page-'+name+'"' in h
    assert '/static/workspace-pages.js' in h and '/static/workspace-pages.css' in h
def test_modules_moved_out_of_approvals():
    for script,view in [('autopilot.js','page-autopilot'),('optimize.js','page-campaigns'),
                        ('advisor.js','page-alerts'),('commercial.js','page-license')]:
        js=(S/script).read_text(encoding='utf-8')
        assert view in js
    core=(S/'studio.js').read_text(encoding='utf-8')
    assert "reports:'Báo cáo'" in core
def test_reports_use_real_data_and_same_currency():
    js=(S/'workspace-pages.js').read_text(encoding='utf-8')
    assert '/api/summary?period=' in js
    assert 'r.currency!==currency' in js
    assert '/api/export/reports?period=' in js
    assert 't.contains_demo' in js
    assert 'Math.random' not in js
    assert 'https://' not in js
