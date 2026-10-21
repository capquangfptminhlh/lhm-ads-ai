"""Tests for tools/acceptance_preflight.py — the offline pre-acceptance gate.

The preflight must (a) pass everything checkable on a correctly configured
machine, (b) treat missing provider credentials as NOT_RUN (a config state,
not a defect), and (c) FAIL — with a non-zero exit code — when core secrets
are missing or malformed. Secret values are never asserted anywhere; only
presence and structure are.
"""
import base64
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "acceptance_preflight", ROOT / "tools" / "acceptance_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf = _load()

FULL_ENV = {
    "MASTER_KEY": base64.b64encode(b"x" * 32).decode(),
    "SESSION_SECRET": "s" * 48,
    "GOOGLE_OAUTH_CLIENT_ID": "gid",
    "GOOGLE_OAUTH_CLIENT_SECRET": "gsecret",
    "GOOGLE_ADS_DEVELOPER_TOKEN": "devtoken",
    "META_APP_ID": "metaid",
    "META_APP_SECRET": "metasecret",
}


def _env(tmp_path, **overrides):
    env = dict(FULL_ENV, DB_PATH=str(tmp_path / "ads.sqlite3"))
    env.update(overrides)
    return env


def _rows(result, title):
    return next(s["rows"] for s in result["sections"] if s["title"] == title)


def test_structure_has_all_sections(tmp_path):
    result = pf.run_preflight(_env(tmp_path))
    titles = [s["title"] for s in result["sections"]]
    assert titles == ["Ứng dụng", "Môi trường lõi", "Nhà cung cấp Ads / AI",
                      "Tài nguyên tĩnh", "Phiên bản API", "Giấy phép"]
    for section in result["sections"]:
        assert section["rows"], section["title"]
        for row in section["rows"]:
            assert row["status"] in (pf.PASS, pf.FAIL, pf.NOT_RUN)


def test_fully_configured_env_has_no_fail(tmp_path):
    result = pf.run_preflight(_env(tmp_path))
    assert result["summary"][pf.FAIL] == 0
    assert pf.exit_code(result) == 0
    providers = _rows(result, "Nhà cung cấp Ads / AI")
    google = next(r for r in providers if r["name"].startswith("Google Ads: GOOGLE"))
    meta = next(r for r in providers if r["name"].startswith("Meta Ads: META"))
    assert google["status"] == pf.PASS and meta["status"] == pf.PASS


def test_missing_provider_env_is_not_run_not_fail(tmp_path):
    env = _env(tmp_path)
    for name in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                 "GOOGLE_ADS_DEVELOPER_TOKEN", "META_APP_ID", "META_APP_SECRET"):
        env.pop(name)
    result = pf.run_preflight(env)
    providers = _rows(result, "Nhà cung cấp Ads / AI")
    google = next(r for r in providers if r["name"].startswith("Google Ads: GOOGLE"))
    assert google["status"] == pf.NOT_RUN
    # NOT_RUN alone must not fail the gate.
    assert result["summary"][pf.FAIL] == 0
    assert pf.exit_code(result) == 0


def test_missing_core_secret_fails_and_exits_nonzero(tmp_path):
    env = _env(tmp_path)
    env.pop("MASTER_KEY")
    result = pf.run_preflight(env)
    core = _rows(result, "Môi trường lõi")
    master = next(r for r in core if r["name"] == "MASTER_KEY")
    assert master["status"] == pf.FAIL
    assert pf.exit_code(result) == 1


def test_malformed_master_key_fails(tmp_path):
    result = pf.run_preflight(_env(tmp_path, MASTER_KEY="not-base64!!"))
    core = _rows(result, "Môi trường lõi")
    master = next(r for r in core if r["name"] == "MASTER_KEY")
    assert master["status"] == pf.FAIL
    short = pf.run_preflight(_env(tmp_path, SESSION_SECRET="too-short"))
    core = _rows(short, "Môi trường lõi")
    secret = next(r for r in core if r["name"] == "SESSION_SECRET")
    assert secret["status"] == pf.FAIL


def test_openrouter_is_informational_not_run(tmp_path):
    result = pf.run_preflight(_env(tmp_path))
    providers = _rows(result, "Nhà cung cấp Ads / AI")
    row = next(r for r in providers if r["name"].startswith("OpenRouter"))
    assert row["status"] == pf.NOT_RUN
    assert "Cài đặt" in row["detail"]  # configured in-app, not via env


def test_app_health_and_license_selftest_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ads.sqlite3"))
    monkeypatch.setenv("MASTER_KEY", FULL_ENV["MASTER_KEY"])
    monkeypatch.setenv("SESSION_SECRET", FULL_ENV["SESSION_SECRET"])
    result = pf.run_preflight(_env(tmp_path))
    app_rows = _rows(result, "Ứng dụng")
    assert all(r["status"] == pf.PASS for r in app_rows)
    license_rows = _rows(result, "Giấy phép")
    assert all(r["status"] == pf.PASS for r in license_rows), license_rows


def test_main_json_mode_and_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ads.sqlite3"))
    for name, value in FULL_ENV.items():
        monkeypatch.setenv(name, value)
    assert pf.main(["--json"]) == 0
    out = capsys.readouterr().out
    assert '"summary"' in out and '"sections"' in out


def test_cli_subprocess_exit_codes(tmp_path):
    import os
    import subprocess
    env = dict(os.environ, **FULL_ENV, DB_PATH=str(tmp_path / "ads.sqlite3"))
    ok = subprocess.run([sys.executable, "tools/acceptance_preflight.py"],
                        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='strict')
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "Tổng kết" in ok.stdout
    bad_env = {k: v for k, v in env.items() if k != "MASTER_KEY"}
    bad = subprocess.run([sys.executable, "tools/acceptance_preflight.py"],
                         cwd=ROOT, env=bad_env, capture_output=True, text=True, encoding='utf-8', errors='strict')
    assert bad.returncode == 1
