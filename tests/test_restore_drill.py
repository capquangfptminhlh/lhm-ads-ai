"""The backup/restore drill as a regression test (all in tmp dirs).

Complements tests/test_secure_backup.py (HTTP-level) by exercising the
offline path exactly as support runs it: seed -> project export functions
-> project restore function -> row/password/checksum verification, plus
fail-closed behaviour for a wrong passphrase and a tampered file.
"""
import importlib.util
from pathlib import Path
import sqlite3

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "restore_drill", ROOT / "tools" / "restore_drill.py")
drill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drill)

from ads_core import secure_backup  # noqa: E402


def test_full_drill_passes(tmp_path):
    checks = drill.run_drill(tmp_path)
    failures = [label for label, ok, _ in checks if not ok]
    assert failures == [], f"drill failures: {failures}"
    assert len(checks) >= 12


def test_wrong_passphrase_fails_closed(tmp_path):
    drill.run_drill(tmp_path)
    blob = (tmp_path / "lhm-ads-backup-drill.lhmbak").read_bytes()
    with pytest.raises(ValueError):
        secure_backup.decrypt_snapshot(blob, "hoan toan sai mat khau 2026")
    # And a restore attempt with the wrong passphrase must not write data.
    empty = tmp_path / "empty-2"
    with pytest.raises(ValueError):
        secure_backup.restore_into_empty_directory(
            blob, "hoan toan sai mat khau 2026", empty)
    assert not (empty / "data" / "lhm-ads.sqlite3").exists()


def test_tampered_backup_fails_integrity(tmp_path):
    drill.run_drill(tmp_path)
    blob = bytearray((tmp_path / "lhm-ads-backup-drill.lhmbak").read_bytes())
    blob[len(blob) // 2] ^= 1
    with pytest.raises(ValueError):
        secure_backup.decrypt_snapshot(bytes(blob), drill.DRILL_PASSPHRASE)


def test_restored_database_is_standalone(tmp_path):
    drill.run_drill(tmp_path)
    restored = tmp_path / "may-moi" / "data" / "lhm-ads.sqlite3"
    with sqlite3.connect(restored) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
