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
            self.assertFalse((out/'ads_core').exists())
            self.assertFalse((out/'.env').exists())
            self.assertFalse((out/'requirements.txt').exists())
            self.assertFalse((out/'docker-compose.yml').exists())
            studio=(out/'studio/index.html').read_text()
            self.assertIn('id="lhm-static-api-guard"',studio)
            self.assertIn('cloudflare-hosting-gate.js',studio)
            self.assertIn('đăng nhập',studio.lower())
            self.assertEqual(json.loads((out/'manifest.webmanifest').read_text())['start_url'],'/studio')
            js=(out/'static/cloudflare-hosting-gate.js').read_text()
            self.assertIn("data?.auth_ready === true && data?.device_only_ready === true",js)
            self.assertIn("credentials: 'same-origin'",js)
            self.assertIn("event.stopImmediatePropagation()",js)

    def test_cloudflare_production_route_and_commercial_policy(self):
        cfg=(ROOT/'wrangler.toml').read_text(encoding='utf-8')
        worker=(ROOT/'workers/ads-api/src/index.js').read_text(encoding='utf-8')
        workflow=(ROOT/'.github/workflows/github-pages-pwa.yml').read_text(encoding='utf-8')
        assert 'pattern = "ads.lhm.com"' in cfg
        assert 'custom_domain = true' in cfg
        assert 'directory = "./_site"' in cfg
        assert 'run_worker_first = ["/api/*"]' in cfg
        assert "auth_ready:false" in worker\n        assert "device_only_ready:false" in worker\n        assert "ads_credential_custody:'device_only'" in worker
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
