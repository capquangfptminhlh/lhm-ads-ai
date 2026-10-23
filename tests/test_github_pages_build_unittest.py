"""No backend or credentials can accidentally be published as GitHub Pages static output."""
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
            self.assertEqual((out/'CNAME').read_text().strip(),'ads.lhm.com')
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
            self.assertIn('github-pages-gate.js',studio)
            self.assertIn('đăng nhập',studio.lower())
            self.assertEqual(json.loads((out/'manifest.webmanifest').read_text())['start_url'],'/studio')
            js=(out/'static/github-pages-gate.js').read_text()
            self.assertIn("data?.auth_ready === true",js)
            self.assertIn("credentials: 'same-origin'",js)
            self.assertIn("event.stopImmediatePropagation()",js)

    def test_existing_source_not_mutated(self):
        original=(ROOT/'static/studio.html').read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            build(Path(temp)/'published')
        self.assertEqual((ROOT/'static/studio.html').read_bytes(),original)
        self.assertNotIn(b'lhm-static-api-guard',original)


if __name__=='__main__':
    unittest.main()
