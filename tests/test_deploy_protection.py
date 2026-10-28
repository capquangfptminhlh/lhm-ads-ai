"""Keep Cloudflare production deployment from publishing draft code to main."""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/deploy-commerce.yml"


class DeployGuardTests(unittest.TestCase):
    def test_production_deploy_requires_merged_main(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.ref != 'refs/heads/main'", text)
        self.assertIn("Production deploy requires a reviewed and merged main branch.", text)

    def test_deployment_cannot_write_unreviewed_github_commits(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("git push origin HEAD:main", text)
        self.assertNotIn("git commit -m", text)
        self.assertIn("git diff --quiet -- wrangler.toml", text)
        self.assertIn("Commit it via a PR first.", text)


if __name__ == "__main__":
    unittest.main()
