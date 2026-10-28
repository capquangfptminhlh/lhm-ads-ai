"""tests/fixtures/core/parity.json must match what the Windows app computes today.

The PWA's JS core is checked against that file (tests/core_parity.test.mjs), so a
change to ads_core that is not regenerated here would let the PWA drift silently.
Runs in a subprocess because the generator patches ads_core with fake clients.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_parity_fixtures_are_regenerated():
    result = subprocess.run([sys.executable, "tools/gen_core_fixtures.py", "--check"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
