"""Static production-domain/HTTPS/OAuth regression for ads.lhm.com.

Does not claim DNS, certificate issuance, OAuth permissions or VPS deployment.
"""
from pathlib import Path
from ads_core.oauth_connect import callback_url, app_origin

ROOT = Path(__file__).resolve().parents[1]


def test_exact_public_oauth_origin(monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://ads.lhm.com')
    assert app_origin() == 'https://ads.lhm.com'
    assert callback_url('google') == 'https://ads.lhm.com/api/oauth/google/callback'
    assert callback_url('meta') == 'https://ads.lhm.com/api/oauth/meta/callback'


def test_production_proxy_tls_and_local_only_backend():
    base = (ROOT/'docker-compose.yml').read_text(encoding='utf-8')
    overlay = (ROOT/'compose.ads-lhm-com.yml').read_text(encoding='utf-8')
    proxy = (ROOT/'deploy/Caddyfile').read_text(encoding='utf-8')
    env = (ROOT/'.env.example').read_text(encoding='utf-8')
    assert '"127.0.0.1:8080:8080"' in base
    assert 'PUBLIC_BASE_URL=https://ads.lhm.com' in env
    assert 'PUBLIC_BASE_URL: https://ads.lhm.com' in overlay
    assert 'COOKIE_SECURE: "true"' in overlay
    assert '"80:80"' in overlay and '"443:443"' in overlay
    assert 'ads.lhm.com {' in proxy and 'reverse_proxy ads-ai:8080' in proxy
    assert 'https://ads.lhm.com/api/oauth/google/callback' in (
        ROOT/'docs/DEPLOY_ADS_LHM_COM.md').read_text(encoding='utf-8')
