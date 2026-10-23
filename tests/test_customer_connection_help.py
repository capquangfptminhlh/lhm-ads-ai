"""Customer connection help ships with Windows Studio, works without web access."""
from pathlib import Path
from fastapi.testclient import TestClient
from ads_core.extended import app

ROOT=Path(__file__).resolve().parents[1]
def load(path):return (ROOT/path).read_text(encoding='utf-8')


def test_dialog_is_accessible_from_accounts_and_settings():
    html=load('static/studio.html')
    js=load('static/customer-help.js')
    css=load('static/customer-help.css')
    assert 'id="customer-help-dialog"' in html
    assert 'aria-labelledby="customer-help-title"' in html
    assert html.count('data-customer-help="google"')>=3
    assert 'id="customer-help-start"' in html
    assert 'role="tablist"' in html
    for mode in ('google','meta','mcp','errors'):
        assert f'data-help-tab="{mode}"' in html
    assert "dialog.showModal()" in js
    assert "dialog.close()" in js
    assert "event.key==='Home'" in js and "event.key==='End'" in js
    assert "new CustomEvent('lhm:open-connect-guide'" in js
    assert '@media(max-width:650px)' in css
    assert 'env(safe-area-inset-bottom)' in css
    assert '@media(prefers-reduced-motion:reduce)' in css


def test_guide_is_packaged_locally_and_printable():
    html=load('static/huong-dan-ket-noi.html')
    css=load('static/customer-help-print.css')
    win=load('.github/workflows/windows-exe.yml')
    for phrase in ('Google Ads API', 'Meta Ads API', 'MCP', 'Kiểm tra API', 'Client Secret'):
        assert phrase in html
    assert 'href="customer-help-print.css"' in html
    assert '@media print' in css and '@page' in css
    assert 'dist/HUONG-DAN-KET-NOI.html' in win
    assert 'dist/customer-help-print.css' in win
    assert 'node --check static/customer-help.js' in win
    assert '/static/customer-help.js' in load('static/studio.html')


def test_offline_guide_is_served_by_local_static_server():
    with TestClient(app) as client:
        r=client.get('/static/huong-dan-ket-noi.html')
        assert r.status_code==200
        assert 'Kết nối Google Ads và Meta Ads' in r.text
        assert 'https://developers.facebook.com/apps/' in r.text
        stylesheet=client.get('/static/customer-help-print.css')
        assert stylesheet.status_code==200
        assert '@media print' in stylesheet.text


def test_help_content_does_not_send_secrets_outside_machine():
    js=load('static/customer-help.js')
    for forbidden in ('fetch(', 'XMLHttpRequest(', 'localStorage', 'openrouter.ai', 'api.openai.com'):
        assert forbidden not in js
    assert 'chưa tích hợp MCP server trực tiếp' in js
    assert 'không phải dữ liệu thực' in js
    assert 'Bắt đầu kết nối' in js
    assert "content.innerHTML=sections[section]" in js
