"""PWA installability regression without caching tenant or provider data."""
from pathlib import Path
from fastapi.testclient import TestClient
from ads_core.extended import app

ROOT = Path(__file__).resolve().parents[1] / "static"

def test_pwa_manifest_and_scope():
    with TestClient(app) as client:
        r = client.get('/manifest.webmanifest')
        assert r.status_code == 200
        assert r.headers['content-type'].startswith('application/manifest+json')
        data = r.json()
        assert data['start_url'] == '/studio'
        assert data['display'] == 'standalone'
        for icon in data['icons']:
            assert client.get(icon['src']).status_code == 200
        sw = client.get('/sw.js')
        assert sw.status_code == 200
        assert sw.headers['service-worker-allowed'] == '/'
        assert client.get('/static/pwa-offline.html').status_code == 200

def test_studio_installs_without_caching_authenticated_data():
    html = (ROOT / "studio.html").read_text(encoding="utf-8")
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert 'rel="manifest"' in html
    assert '/static/pwa-install.js' in html
    assert "req.mode === 'navigate'" in sw
    assert "url.pathname.startsWith('/api/')" in sw
    assert "url.pathname.startsWith('/static/')" in sw
    assert "cache.put(req, copy)" in sw
    assert "cache.put(req, copy)" not in sw.split("if (req.mode === 'navigate')")[1].split("if (url.pathname.startsWith('/api/')")[0]

def test_pwa_assets_exist_and_no_third_party_endpoint():
    for name in ('pwa-mobile.css','pwa-install.js','sw.js','pwa-offline.html','pwa-offline.css','pwa-offline.js'):
        assert (ROOT / name).is_file()
    script = (ROOT / 'pwa-install.js').read_text(encoding='utf-8')
    assert "serviceWorker.register('/sw.js'" in script
    assert 'https://' not in script
