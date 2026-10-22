"""Round-2 legacy-codepage sweep (Windows cp1252) regression tests.

Round 1 (2026-10-21/22) pinned UTF-8 streams in the tools/ seller CLIs and
made the tests decode subprocess output as UTF-8. This sweep audited every
remaining CLI entry point and found two gaps, both reproduced before fixing:

* ``ads_core.cli`` (``python -m ads_core.cli create-admin``) prompts and
  reports in Vietnamese but never pinned its streams: under cp1252 the
  admin row was inserted and then the success print crashed with
  UnicodeEncodeError.
* ``windows/launcher.py`` did reconfigure its streams, but only inside
  ``configure_windowed_logs()`` — which runs AFTER
  ``configure_local_storage()``. A failure there (Vietnamese messages from
  ads_core.windows_vault, e.g. a corrupt local-settings.json) printed its
  traceback and fallback error text before the pinning happened, landing
  backslash-mangled on a legacy-codepage console.

Every subprocess below runs with PYTHONIOENCODING=cp1252 and LC_ALL=C —
the same simulation the round-1 regression test uses — and its raw output
bytes must decode as strict UTF-8.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {'PYTHONIOENCODING': 'cp1252', 'LC_ALL': 'C'}


def run_legacy(args, env_extra=None, timeout=180):
    env = dict(os.environ, **LEGACY)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, *args], cwd=str(ROOT), env=env,
                          capture_output=True, timeout=timeout)
    # errors='strict': a child emitting legacy-codepage bytes fails here.
    return (proc.returncode,
            proc.stdout.decode('utf-8', errors='strict'),
            proc.stderr.decode('utf-8', errors='strict'))


# Every argparse CLI in the repo: round-1 pinned tools, the round-2 fixes,
# and prepare_commercial_build (ASCII-only output, included for coverage).
HELP_CASES = [
    ('tools/vendor_ledger.py', None),
    ('tools/license_issuer.py', None),
    ('tools/license_revoke.py', None),
    # customer_restore imports ads_core but, run as a plain script, only
    # resolves it with the repo root on PYTHONPATH (pre-existing trait).
    ('tools/customer_restore.py', {'PYTHONPATH': str(ROOT)}),
    ('tools/acceptance_preflight.py', None),
    ('tools/payos_webhook_server.py', None),
    ('tools/prepare_commercial_build.py', None),
    ('windows/launcher.py', None),
]


@pytest.mark.parametrize('script,env_extra', HELP_CASES,
                         ids=[c[0] for c in HELP_CASES])
def test_cli_help_survives_legacy_codepage(script, env_extra):
    code, out, err = run_legacy([script, '--help'], env_extra=env_extra)
    assert code == 0, err
    assert 'usage' in out.lower()


def test_ads_core_cli_help_survives_legacy_codepage():
    code, out, err = run_legacy(['-m', 'ads_core.cli', '--help'])
    assert code == 0, err
    assert 'create-admin' in out


def test_license_issuer_help_is_real_utf8_vietnamese():
    # The keygen subcommand's help contains Vietnamese strings; they must
    # arrive as genuine UTF-8, not replacement characters.
    code, out, err = run_legacy(['tools/license_issuer.py', 'keygen', '--help'])
    assert code == 0, err
    assert 'chứa' in out


def test_restore_drill_survives_legacy_codepage():
    # restore_drill has no argparse: a bare run IS its no-op invocation
    # (self-contained, works in a temp dir, prints a Vietnamese report).
    code, out, err = run_legacy(['tools/restore_drill.py'])
    assert code == 0, err
    assert 'KẾT QUẢ' in out


def test_ads_core_cli_create_admin_end_to_end(tmp_path):
    """The round-2 crash: success print after the admin insert.

    getpass is stubbed inside the child so the run is non-interactive and
    portable; the child's streams still start as cp1252 via the env, which
    is exactly the condition that crashed before the fix.
    """
    driver = (
        "import sys, getpass\n"
        "sys.argv = ['ads_core.cli', 'create-admin', '--email', 'sweep@test.local']\n"
        "getpass.getpass = lambda prompt='': 'sweep_password_123'\n"
        "from ads_core.cli import main\n"
        "main()\n"
    )
    code, out, err = run_legacy(
        ['-c', driver],
        env_extra={'DB_PATH': str(tmp_path / 'ads.sqlite3')})
    assert code == 0, err
    assert 'Đã tạo admin' in out


def test_launcher_corrupt_settings_diagnostics_are_utf8(tmp_path):
    """Vietnamese startup diagnostics must render as UTF-8 even when the
    failure happens before configure_windowed_logs() would have run."""
    (tmp_path / 'local-settings.json').write_text(
        json.dumps({'bogus': True}), encoding='utf-8')
    code, out, err = run_legacy(
        ['windows/launcher.py', '--headless', '--port', '18799'],
        env_extra={'LHM_DATA_DIR': str(tmp_path)}, timeout=60)
    assert code == 1  # corrupt settings still fail closed
    assert 'Tệp cấu hình bảo mật bị hỏng' in err
    assert 'Ứng dụng chưa khởi động được' in err
