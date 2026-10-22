"""Offline acceptance preflight for LHM Ads AI (no network, no real accounts).

Checks everything that can be checked BEFORE the owner runs the live
acceptance in docs/ACCEPTANCE.md with real Google/Meta accounts:

  1. The app imports and answers /healthz and /studio (FastAPI TestClient).
  2. Core environment (MASTER_KEY / SESSION_SECRET) is present and well-formed.
  3. Provider environment names — read from the adapter code, never guessed:
       Google: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
               GOOGLE_ADS_DEVELOPER_TOKEN (optional: GOOGLE_ADS_API_VERSION)
       Meta:   META_APP_ID, META_APP_SECRET
               (optional: META_GRAPH_VERSION, META_OAUTH_SCOPES)
     Missing provider config is NOT_RUN (not configured yet), not a defect.
  4. OpenRouter has no env config at all — its key lives in the in-app
     settings (per-org, encrypted), so it is reported NOT_RUN/informational.
  5. Static assets ship complete, including the bundled Inter font CSS.
  6. Provider API version defaults agree at every read site in the code.
  7. License self-test, fully offline: a throwaway Ed25519 key pair signs a
     test license and ads_core.licensing verifies it (with the pinned public
     key temporarily swapped for the throwaway one, then restored); a
     tampered copy must be rejected.
  8. Optimization stack, STATIC source checks only: the playbook module
     imports with >= 16 uniquely-coded rules and a condition (or an
     account-level evaluator) for every code; advisor.py references the
     playbook evaluation plus the snapshot/outcome tables; the Google/Meta
     adapters request the bid fields; the skill doc names the rules. These
     prove the code ships wired — they are NOT live proof against a real
     ad account, which stays with the real-account acceptance.

Exit code is non-zero when any row is FAIL. Secret values are never printed.

Usage:  python tools/acceptance_preflight.py [--json]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS, FAIL, NOT_RUN = "PASS", "FAIL", "NOT_RUN"

GOOGLE_REQUIRED = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                   "GOOGLE_ADS_DEVELOPER_TOKEN")
GOOGLE_OPTIONAL = ("GOOGLE_ADS_API_VERSION",)
META_REQUIRED = ("META_APP_ID", "META_APP_SECRET")
META_OPTIONAL = ("META_GRAPH_VERSION", "META_OAUTH_SCOPES")
CORE_REQUIRED = ("MASTER_KEY", "SESSION_SECRET")


def _row(name: str, status: str, detail: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail}


def _present(env: dict, name: str) -> bool:
    return bool(str(env.get(name, "")).strip())


def check_app() -> list[dict]:
    rows = []
    try:
        from fastapi.testclient import TestClient
        from ads_core.extended import app
        rows.append(_row("Import ads_core.extended", PASS))
    except Exception as exc:  # import failure is exactly what preflight is for
        rows.append(_row("Import ads_core.extended", FAIL, f"{type(exc).__name__}: {exc}"))
        return rows
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            health = client.get("/healthz")
            health_body = health.json() if health.status_code == 200 else {}
            rows.append(_row("GET /healthz", PASS if health.status_code == 200
                             and isinstance(health_body, dict)
                             and health_body.get("ok") is True else FAIL,
                             f"HTTP {health.status_code}"))
            studio = client.get("/studio")
            rows.append(_row("GET /studio", PASS if studio.status_code == 200 else FAIL,
                             f"HTTP {studio.status_code}"))
    except Exception as exc:
        rows.append(_row("TestClient khởi động", FAIL, f"{type(exc).__name__}: {exc}"))
    return rows


def check_core_env(env: dict) -> list[dict]:
    rows = []
    master = str(env.get("MASTER_KEY", ""))
    if not master:
        rows.append(_row("MASTER_KEY", FAIL, "chưa đặt — app không thể mã hóa vault"))
    else:
        try:
            raw = base64.b64decode(master, validate=True)
            rows.append(_row("MASTER_KEY", PASS if len(raw) == 32 else FAIL,
                             "base64 của 32 bytes" if len(raw) == 32
                             else f"base64 hợp lệ nhưng {len(raw)} bytes (cần 32)"))
        except Exception:
            rows.append(_row("MASTER_KEY", FAIL, "không phải base64 hợp lệ"))
    secret = str(env.get("SESSION_SECRET", ""))
    if not secret:
        rows.append(_row("SESSION_SECRET", FAIL, "chưa đặt"))
    else:
        rows.append(_row("SESSION_SECRET", PASS if len(secret) >= 32 else FAIL,
                         f"{len(secret)} ký tự" + ("" if len(secret) >= 32 else " (cần ≥ 32)")))
    rows.append(_row("DB_PATH", PASS if _present(env, "DB_PATH") else NOT_RUN,
                     "đã đặt" if _present(env, "DB_PATH")
                     else "chưa đặt — app dùng ./data/lhm-ads.sqlite3"))
    return rows


def _provider_rows(env: dict, label: str, required: tuple, optional: tuple,
                   hint: str) -> list[dict]:
    missing = [n for n in required if not _present(env, n)]
    if missing:
        rows = [_row(f"{label}: {', '.join(required)}", NOT_RUN,
                     f"chưa cấu hình ({', '.join(missing)}) — {hint}")]
    else:
        rows = [_row(f"{label}: {', '.join(required)}", PASS, "đã có mặt (không in giá trị)")]
    for name in optional:
        rows.append(_row(f"{label}: {name} (tùy chọn)",
                         PASS if _present(env, name) else NOT_RUN,
                         "đã đặt" if _present(env, name) else "chưa đặt — dùng mặc định của code"))
    return rows


def check_providers(env: dict) -> list[dict]:
    rows = _provider_rows(env, "Google Ads", GOOGLE_REQUIRED, GOOGLE_OPTIONAL,
                          "cần cho bước nghiệm thu trực tiếp mục A trong docs/ACCEPTANCE.md")
    rows += _provider_rows(env, "Meta Ads", META_REQUIRED, META_OPTIONAL,
                           "cần cho bước nghiệm thu trực tiếp mục B trong docs/ACCEPTANCE.md")
    rows.append(_row("OpenRouter (AI ngoài, tùy chọn)", NOT_RUN,
                     "không cấu hình qua env — khóa API nằm trong Cài đặt của app "
                     "(mã hóa theo từng tổ chức); kiểm tra trực tiếp trong app"))
    tg_missing = [n for n in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not _present(env, n)]
    rows.append(_row("Telegram cảnh báo (tùy chọn)",
                     NOT_RUN if tg_missing else PASS,
                     "chưa cấu hình — cảnh báo chỉ hiện trong app" if tg_missing else "đã cấu hình"))
    return rows


def check_static() -> list[dict]:
    static = ROOT / "static"
    required = ("studio.html", "setup.html", "setup.js", "studio.js",
                "finpoint-theme.css", "finpoint-motion.css", "workspace-pages.css")
    rows = []
    for name in required:
        f = static / name
        rows.append(_row(f"static/{name}", PASS if f.exists() and f.stat().st_size > 0 else FAIL,
                         "" if f.exists() else "thiếu file"))
    fonts = static / "fonts.css"
    if fonts.exists():
        text = fonts.read_text(encoding="utf-8")
        faces = text.count("@font-face")
        rows.append(_row("static/fonts.css (Inter đóng gói)",
                         PASS if faces >= 3 and "data:font/woff2;base64," in text else FAIL,
                         f"{faces} @font-face"))
    else:
        rows.append(_row("static/fonts.css (Inter đóng gói)", FAIL, "thiếu file"))
    lic = static / "fonts" / "LICENSE-Inter.txt"
    rows.append(_row("static/fonts/LICENSE-Inter.txt", PASS if lic.exists() else FAIL,
                     "" if lic.exists() else "thiếu giấy phép font"))
    return rows


def _defaults(pattern: str) -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "ads_core").glob("*.py"):
        found.update(re.findall(pattern, path.read_text(encoding="utf-8")))
    return found


def check_versions() -> list[dict]:
    rows = []
    google = _defaults(r"GOOGLE_ADS_API_VERSION\W{1,16}?(v\d+)")
    rows.append(_row("Mặc định GOOGLE_ADS_API_VERSION tại mọi điểm đọc",
                     PASS if len(google) == 1 else FAIL,
                     ", ".join(sorted(google)) or "không tìm thấy"))
    meta = _defaults(r"META_GRAPH_VERSION\W{1,16}?(v\d+\.\d+)")
    rows.append(_row("Mặc định META_GRAPH_VERSION tại mọi điểm đọc",
                     PASS if len(meta) == 1 else FAIL,
                     ", ".join(sorted(meta)) or "không tìm thấy"))
    try:
        from ads_core.release_info import EDITION
        rows.append(_row("release_info.EDITION", PASS,
                         f"EDITION='{EDITION}' (bản thương mại được gán khi build Windows)"))
    except Exception as exc:
        rows.append(_row("release_info.EDITION", FAIL, f"{type(exc).__name__}: {exc}"))
    return rows


def check_license(env: dict) -> list[dict]:
    """Throwaway-key sign + verify round-trip against ads_core.licensing."""
    rows = []
    try:
        import ads_core.licensing as licensing
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey)
        from cryptography.hazmat.primitives import serialization
    except Exception as exc:
        rows.append(_row("Giấy phép: import module", FAIL, f"{type(exc).__name__}: {exc}"))
        return rows
    db_path = str(env.get("DB_PATH", "")).strip()
    old_db_path = os.environ.get("DB_PATH")
    old_key = licensing.PUBLIC_KEY_B64
    try:
        if db_path:
            os.environ["DB_PATH"] = db_path  # keep install-id inside the temp folder
        key = Ed25519PrivateKey.generate()
        public_b64 = base64.b64encode(key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode("ascii")
        now = int(time.time())
        payload = {"product": licensing.PRODUCT, "device": licensing.device_id(),
                   "license_id": "preflight-selftest", "issued_at": now,
                   "expires_at": now + 86400, "plan": "trial"}
        envelope = {"payload": payload,
                    "signature": base64.b64encode(
                        key.sign(licensing.canonical(payload))).decode("ascii")}
        licensing.PUBLIC_KEY_B64 = public_b64
        verified = licensing.verify_signed_license(json.dumps(envelope), now=now)
        rows.append(_row("Giấy phép: ký thử + xác minh (khóa dùng một lần)",
                         PASS if verified["license_id"] == "preflight-selftest" else FAIL,
                         "vòng ký–xác minh offline hoàn chỉnh"))
        tampered = dict(envelope, signature=base64.b64encode(b"\x00" * 64).decode("ascii"))
        try:
            licensing.verify_signed_license(json.dumps(tampered), now=now)
            rows.append(_row("Giấy phép: bản bị sửa phải bị từ chối", FAIL,
                             "chữ ký sai vẫn được chấp nhận"))
        except ValueError:
            rows.append(_row("Giấy phép: bản bị sửa phải bị từ chối", PASS, "đã từ chối đúng"))
    except Exception as exc:
        rows.append(_row("Giấy phép: ký thử + xác minh (khóa dùng một lần)", FAIL,
                         f"{type(exc).__name__}: {exc}"))
    finally:
        licensing.PUBLIC_KEY_B64 = old_key
        if db_path:
            if old_db_path is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = old_db_path
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "license_issuer", ROOT / "tools" / "license_issuer.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ok = hasattr(module, "create_vendor_keys") and hasattr(module, "main")
        rows.append(_row("tools/license_issuer.py (công cụ phát hành offline)",
                         PASS if ok else FAIL, "" if ok else "thiếu entrypoint"))
    except Exception as exc:
        rows.append(_row("tools/license_issuer.py (công cụ phát hành offline)", FAIL,
                         f"{type(exc).__name__}: {exc}"))
    return rows


def check_optimization() -> list[dict]:
    """Static readiness of the optimization stack.

    Source-level checks ONLY: they prove the playbook, the advisor wiring,
    the adapter bid fields and the skill doc ship together in this tree.
    Nothing here calls a provider or proves live behaviour — that stays
    NOT_RUN territory until the owner runs the real-account acceptance.
    """
    rows = []
    try:
        from ads_core import optimization_playbook as playbook
        rows.append(_row("Ngăn xếp tối ưu: import ads_core.optimization_playbook", PASS))
    except Exception as exc:
        rows.append(_row("Ngăn xếp tối ưu: import ads_core.optimization_playbook", FAIL,
                         f"{type(exc).__name__}: {exc}"))
        return rows
    codes = [entry.get("code") for entry in playbook.PLAYBOOK]
    unique = len(set(codes)) == len(codes)
    # Campaign-level rules dispatch through CONDITIONS; the account-level
    # rules are evaluated by evaluate_account (which looks them up by code).
    import inspect
    account_src = inspect.getsource(playbook.evaluate_account)
    account_level = [c for c in codes if c not in playbook.CONDITIONS]
    uncovered = [c for c in account_level if c not in account_src]
    ok = len(codes) >= 16 and unique and not uncovered
    detail = (f"{len(codes)} quy tắc: {len(playbook.CONDITIONS)} điều kiện cấp chiến dịch"
              f" + {len(account_level)} quy tắc cấp tài khoản qua evaluate_account")
    if not unique:
        detail += "; TRÙNG mã quy tắc"
    if uncovered:
        detail += f"; mã chưa có điều kiện: {', '.join(uncovered)}"
    rows.append(_row("Ngăn xếp tối ưu: PLAYBOOK ≥ 16 quy tắc, mã duy nhất, mọi mã có điều kiện",
                     PASS if ok else FAIL, detail))
    advisor = ROOT / "ads_core" / "advisor.py"
    advisor_src = advisor.read_text(encoding="utf-8") if advisor.exists() else ""
    static_note = "kiểm tra tĩnh trên mã nguồn — không phải bằng chứng chạy trực tiếp"
    eval_ok = ("optimization_playbook.evaluate_campaigns" in advisor_src
               and "optimization_playbook.evaluate_account" in advisor_src)
    rows.append(_row("Ngăn xếp tối ưu: advisor gọi playbook evaluate_campaigns/evaluate_account",
                     PASS if eval_ok else FAIL, static_note))
    tables_ok = "advisor_snapshots" in advisor_src and "advisor_outcomes" in advisor_src
    rows.append(_row("Ngăn xếp tối ưu: advisor có bảng advisor_snapshots + advisor_outcomes",
                     PASS if tables_ok else FAIL, static_note))
    optimizations = ROOT / "ads_core" / "optimizations.py"
    opt_src = optimizations.read_text(encoding="utf-8") if optimizations.exists() else ""
    google_ok = "bidding_strategy_type" in opt_src and "campaign_budget.amount_micros" in opt_src
    rows.append(_row("Ngăn xếp tối ưu: adapter Google lấy bidding_strategy_type + campaign_budget.amount_micros",
                     PASS if google_ok else FAIL, static_note))
    meta_ok = "bid_strategy,daily_budget" in opt_src  # chuỗi fields của /campaigns
    rows.append(_row("Ngăn xếp tối ưu: adapter Meta lấy bid_strategy trong fields /campaigns",
                     PASS if meta_ok else FAIL, static_note))
    skill = ROOT / "docs" / "OPTIMIZATION_SKILL.md"
    skill_ok = (skill.exists()
                and "platform_target_missed" in skill.read_text(encoding="utf-8"))
    rows.append(_row("Ngăn xếp tối ưu: docs/OPTIMIZATION_SKILL.md mô tả platform_target_missed",
                     PASS if skill_ok else FAIL,
                     "" if skill_ok else "thiếu file hoặc thiếu mã quy tắc trong tài liệu"))
    return rows


class _applied_env:
    """Temporarily apply the env being preflighted so the app boots with
    exactly the configuration under test; restores everything afterwards."""

    def __init__(self, env: dict):
        self._env = env
        self._old: dict = {}

    def __enter__(self):
        for key in ("MASTER_KEY", "SESSION_SECRET", "DB_PATH", "COOKIE_SECURE"):
            if key in self._env:
                self._old[key] = os.environ.get(key)
                os.environ[key] = str(self._env[key])
        return self

    def __exit__(self, *exc):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return False


def run_preflight(env: dict | None = None) -> dict:
    """Run every offline check. `env` defaults to os.environ; values are only
    inspected for presence/format — never returned or printed."""
    env = dict(os.environ) if env is None else dict(env)
    with _applied_env(env):
        app_rows = check_app()
    sections = [
        ("Ứng dụng", app_rows),
        ("Môi trường lõi", check_core_env(env)),
        ("Nhà cung cấp Ads / AI", check_providers(env)),
        ("Tài nguyên tĩnh", check_static()),
        ("Phiên bản API", check_versions()),
        ("Ngăn xếp tối ưu", check_optimization()),
        ("Giấy phép", check_license(env)),
    ]
    result = {"sections": [{"title": t, "rows": r} for t, r in sections]}
    result["summary"] = {
        status: sum(1 for _, rows in sections for r in rows if r["status"] == status)
        for status in (PASS, FAIL, NOT_RUN)}
    return result


def exit_code(result: dict) -> int:
    return 1 if result["summary"][FAIL] else 0


def print_table(result: dict) -> None:
    marks = {PASS: "PASS   ", FAIL: "FAIL   ", NOT_RUN: "NOT_RUN"}
    for section in result["sections"]:
        print(f"\n== {section['title']} ==")
        for row in section["rows"]:
            detail = f" — {row['detail']}" if row["detail"] else ""
            print(f"[{marks[row['status']]}] {row['name']}{detail}")
    s = result["summary"]
    print(f"\nTổng kết: {s[PASS]} PASS · {s[FAIL]} FAIL · {s[NOT_RUN]} NOT_RUN")
    if s[FAIL]:
        print("Kết luận: CHƯA ĐẠT — sửa các dòng FAIL trước khi nghiệm thu trực tiếp.")
    elif s[NOT_RUN]:
        print("Kết luận: phần kiểm tra được tại máy này đã đạt; các dòng NOT_RUN chờ "
              "cấu hình/tài khoản thật theo docs/ACCEPTANCE.md.")
    else:
        print("Kết luận: ĐẠT toàn bộ kiểm tra offline.")


def _force_utf8_streams():
    # Windows consoles/pipes default to a legacy codepage (cp1252/cp437)
    # that cannot encode Vietnamese; these CLIs print Vietnamese status
    # text, so pin stdout/stderr to UTF-8 when the runtime allows it.
    import sys as _sys
    for stream in (_sys.stdout, _sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(description="LHM Ads AI — kiểm tra tiền nghiệm thu (offline)")
    parser.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    args = parser.parse_args(argv)
    result = run_preflight()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_table(result)
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
