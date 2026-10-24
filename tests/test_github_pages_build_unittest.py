"""No backend or credentials can accidentally be published as Cloudflare static assets."""
import json
import tempfile
import unittest
from pathlib import Path
from tools.build_github_pages import build

ROOT=Path(__file__).resolve().parents[1]


class StaticPagesTests(unittest.TestCase):
    def test_static_preview_and_fail_closed_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            out=build(Path(temp)/'site')
            self.assertFalse((out/'CNAME').exists())
            self.assertTrue((out/'static/icons/icon-192.png').exists())
            self.assertTrue((out/'static/icons/icon-512.png').exists())
            self.assertTrue((out/'sw.js').exists())
            self.assertTrue((out/'manifest.webmanifest').exists())
            self.assertTrue((out/'studio/index.html').exists())
            self.assertTrue((out/'local/index.html').exists())
            landing=(out/'index.html').read_text(encoding='utf-8')
            self.assertIn('LHM Ads AI — Không gian quản lý quảng cáo thông minh',landing)
            self.assertIn('<link rel="stylesheet" href="/static/marketing.css">',landing)
            self.assertIn('href="/local/"',landing)
            self.assertIn('id="tinh-nang"',landing)
            self.assertIn('id="bao-mat"',landing)
            self.assertIn('id="bang-gia"',landing)
            self.assertIn('499.000đ',landing)
            self.assertIn('Chưa thu tiền trực tuyến',landing)
            self.assertNotIn('http-equiv="refresh"',landing)
            self.assertNotIn('login-pass',landing)
            self.assertNotIn('accessToken',landing)
            self.assertTrue((out/'static/marketing.css').exists())
            local=(out/'local/index.html').read_text(encoding='utf-8')
            self.assertIn('id="lhm-local-workspace"',local)
            self.assertIn('pwa-gated',local)
            self.assertIn('id="pwa-access-gate"',local)
            self.assertIn('id="pwa-login-portal"',local)
            self.assertIn('id="pwa-signout"',local)
            self.assertIn('href="/"',local)
            self.assertIn('marketing.css',(out/'sw.js').read_text(encoding='utf-8'))
            local_ui=(out/'static/device-studio.js').read_text(encoding='utf-8')
            self.assertIn('syncAccessGate',local_ui)
            self.assertIn('pwa-gated',local_ui)
            self.assertIn('lhm-vault-lock',local_ui)
            self.assertIn('device-vault.js',local)
            self.assertIn('device-insights.js',local)
            self.assertIn('device-mcp.js',local)
            self.assertNotIn('login-form',local)
            worker=(out/'sw.js').read_text(encoding='utf-8')
            self.assertIn("'/local/'",worker)
            self.assertIn("caches.match('/local/')",worker)
            self.assertIn("lhm-pwa-cloudflare-v6-20261024",worker)
            self.assertIn("url.pathname.startsWith('/api/')",worker)
            self.assertNotIn("'/studio/'",worker)

            self.assertFalse((out/'ads_core').exists())
            self.assertFalse((out/'.env').exists())
            self.assertFalse((out/'requirements.txt').exists())
            self.assertFalse((out/'docker-compose.yml').exists())
            studio=(out/'studio/index.html').read_text(encoding='utf-8')
            self.assertIn('id="lhm-static-api-guard"',studio)
            self.assertIn('cloudflare-hosting-gate.js',studio)
            self.assertIn('device-vault.js',studio)
            self.assertIn('device-vault-ui.js',studio)
            self.assertIn('device-insights.js',studio)
            self.assertIn('device-insights.css',studio)
            self.assertIn('soft-motion-ui.css',studio)
            self.assertIn('soft-motion-ui.js',studio)
            self.assertIn('device-studio.css',local)
            self.assertIn('device-studio.js',local)
            self.assertIn('data-view="dashboard"',local)
            self.assertIn('data-view="accounts"',local)
            self.assertIn('data-view="reports"',local)
            self.assertIn('data-view="alerts"',local)
            self.assertIn('data-view="assistant"',local)
            self.assertIn('id="pwa-sidebar"',local)
            self.assertIn('id="lhm-local-workspace"',local)
            self.assertNotIn('src="/static/studio.js"',local)
            self.assertNotIn('api/studio/me',local)
            self.assertIn('device-studio.css',worker)
            self.assertIn('device-studio.js',worker)
            self.assertTrue((out/'static/device-studio.css').exists())
            self.assertTrue((out/'static/device-studio.js').exists())
            new_js=(out/'static/device-studio.js').read_text(encoding='utf-8')
            self.assertNotIn('fetch(',new_js)
            self.assertNotIn('localStorage.',new_js)
            self.assertIn('lhm:vault-locked',new_js)
            self.assertTrue((out/'static/soft-motion-ui.css').exists())
            self.assertTrue((out/'static/soft-motion-ui.js').exists())
            self.assertIn("'/static/soft-motion-ui.css'",worker)
            soft=(out/'static/soft-motion-ui.css').read_text(encoding='utf-8')
            self.assertIn('prefers-reduced-motion',soft)
            self.assertIn('lhm-soft-drift',soft)

            self.assertIn('device-vault.css',studio)
            headers=(out/'_headers').read_text(encoding='utf-8')
            self.assertIn("script-src 'self'",headers)
            self.assertIn("connect-src 'self'",headers)
            self.assertIn("X-Content-Type-Options: nosniff\n",headers)
            self.assertNotIn("\\\\n",headers)
            self.assertIn("object-src 'none'",headers)
            vault=(out/'static/device-vault.js').read_text(encoding='utf-8')
            self.assertIn("AES-GCM",vault)
            insights=(out/'static/device-insights.js').read_text(encoding='utf-8')
            self.assertIn('manual_csv', (ROOT/'static/device-vault.js').read_text(encoding='utf-8'))
            self.assertNotIn('fetch(',insights)
            self.assertNotIn('localStorage.',insights)
            self.assertIn("PBKDF2",vault)
            self.assertNotIn("fetch(",vault)
            self.assertNotIn("localStorage.",vault)

            self.assertIn('đăng nhập',studio.lower())
            self.assertEqual(json.loads((out/'manifest.webmanifest').read_text())['start_url'],'/local/')
            js=(out/'static/cloudflare-hosting-gate.js').read_text()
            self.assertIn("data?.auth_ready === true && data?.device_only_ready === true",js)
            self.assertIn("credentials: 'same-origin'",js)
            self.assertIn("event.stopImmediatePropagation()",js)

    def test_cloudflare_production_route_and_commercial_policy(self):
        cfg=(ROOT/'wrangler.toml').read_text(encoding='utf-8')
        worker=(ROOT/'workers/ads-api/src/index.js').read_text(encoding='utf-8')
        workflow=(ROOT/'.github/workflows/github-pages-pwa.yml').read_text(encoding='utf-8')
        assert 'pattern = "ads.lhmcrm.com"' in cfg
        assert 'custom_domain = true' in cfg
        assert 'directory = "./_site"' in cfg
        assert 'run_worker_first = ["/api/*"]' in cfg
        assert "auth_ready:false" in worker
        assert "device_only_ready:false" in worker
        assert "ads_credential_custody:'device_only'" in worker
        assert "return json({" in worker
        assert "503" in worker
        assert 'env.ASSETS.fetch(request)' in worker
        assert 'deploy-pages' not in workflow
        assert 'pages: write' not in workflow

    def test_existing_source_not_mutated(self):
        original=(ROOT/'static/studio.html').read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            build(Path(temp)/'published')
        self.assertEqual((ROOT/'static/studio.html').read_bytes(),original)
        self.assertNotIn(b'lhm-static-api-guard',original)


if __name__=='__main__':
    unittest.main()
