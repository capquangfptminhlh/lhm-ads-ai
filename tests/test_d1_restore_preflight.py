"""Pre-migration D1 rollback preflight must be read-only and fail closed."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import deploy_commerce

BOOKMARK = "00000085-0000024c-00004c6d-8e61117bf38d7adb71b934ebbf891683"


class RestorePointTests(unittest.TestCase):
    def test_verifies_current_time_travel_bookmark_before_migration(self):
        output = "The current bookmark is '" + BOOKMARK + "'\n" + (
            "wrangler d1 time-travel restore lhm-ads-commerce --bookmark=" + BOOKMARK)
        completed = subprocess.CompletedProcess([], 0, stdout=output, stderr="")
        with patch.object(deploy_commerce.subprocess, "run", return_value=completed) as mocked:
            result = deploy_commerce.confirm_pre_migration_restore_point(Path("wrangler.commerce.generated.toml"))
        self.assertEqual(result, BOOKMARK)
        args = mocked.call_args.args[0]
        self.assertEqual(args[:5], ["npx", "wrangler", "d1", "time-travel", "info"])
        self.assertNotIn("restore", args)
        self.assertNotIn("migrations", args)

    def test_refuses_to_migrate_if_restore_point_unavailable(self):
        for content in ("", "No backups available", "Bookmark is just some random text",
                        "--bookmark=../../bad", "--bookmark=not-a-real-bookmark"):
            with self.subTest(output=content):
                with patch.object(deploy_commerce.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 0, stdout=content, stderr="")):
                    with self.assertRaisesRegex(RuntimeError, "restore bookmark"):
                        deploy_commerce.confirm_pre_migration_restore_point(Path("test.toml"))

    def test_wrangler_failure_blocks_preflight(self):
        with patch.object(deploy_commerce.subprocess, "run",
            side_effect=subprocess.CalledProcessError(1, ["wrangler", "d1", "time-travel", "info"])):
            with self.assertRaises(subprocess.CalledProcessError):
                deploy_commerce.confirm_pre_migration_restore_point(Path("test.toml"))


if __name__ == "__main__":
    unittest.main()
