"""LHM Ads AI Windows desktop entry point. Localhost only, no MCP."""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def data_directory() -> Path:
    override = os.environ.get("LHM_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "LHMAdsAI"
    return Path.home() / ".lhm-ads-ai"


def configure_local_storage() -> Path:
    folder = data_directory()
    folder.mkdir(parents=True, exist_ok=True)
    settings_file = folder / "local-settings.json"
    if settings_file.exists():
        config = json.loads(settings_file.read_text(encoding="utf-8"))
    else:
        config = {
            "MASTER_KEY": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
            "SESSION_SECRET": secrets.token_urlsafe(48),
        }
        fd = os.open(settings_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(config, fh)
    for name in ("MASTER_KEY", "SESSION_SECRET"):
        if not os.environ.get(name):
            os.environ[name] = config[name]
    os.environ.setdefault("DB_PATH", str(folder / "data" / "lhm-ads.sqlite3"))
    os.environ["COOKIE_SECURE"] = "false"  # loopback HTTP only
    return folder


def bootstrap_first_admin(*, headless: bool) -> None:
    from ads_core.db import connection, init_db
    from ads_core.security import hash_password

    init_db()
    with connection() as db:
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count:
        return
    if headless:
        print("No administrator configured (headless smoke test mode).")
        return
    print("\nLẦN ĐẦU SỬ DỤNG — tạo tài khoản quản trị trên máy này")
    while True:
        email = input("Email quản trị: ").strip().lower()
        if "@" in email and "." in email.split("@")[-1]:
            break
        print("Email không hợp lệ. Vui lòng thử lại.")
    while True:
        password = getpass.getpass("Mật khẩu (tối thiểu 12 ký tự): ")
        confirm = getpass.getpass("Nhập lại mật khẩu: ")
        if password == confirm and len(password) >= 12:
            break
        print("Hai mật khẩu chưa khớp hoặc quá ngắn.")
    with connection() as db:
        db.execute("INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)",
                   (email, hash_password(password), "main", "admin"))
    print("Đã tạo tài khoản quản trị trên máy cục bộ.")


def open_browser_after_start(port: int) -> None:
    url = f"http://127.0.0.1:{port}/studio"

    def worker() -> None:
        health = f"http://127.0.0.1:{port}/healthz"
        for _ in range(80):
            try:
                with urllib.request.urlopen(health, timeout=1) as resp:
                    if resp.status == 200:
                        webbrowser.open(url)
                        return
            except Exception:
                pass
            time.sleep(.25)
        print("Không thể mở trình duyệt tự động; truy cập:", url)

    threading.Thread(target=worker, name="open-dashboard", daemon=True).start()


def main() -> None:
    p = argparse.ArgumentParser(description="LHM Ads AI - chạy dashboard an toàn trên máy Windows")
    p.add_argument("--headless", action="store_true", help="Không tạo admin hay mở browser (dành cho CI)")
    p.add_argument("--port", type=int, default=8765, help="Cổng localhost (mặc định 8765)")
    args = p.parse_args()
    if not (1024 <= args.port <= 65535):
        p.error("Cổng phải nằm trong khoảng 1024..65535")
    configure_local_storage()
    bootstrap_first_admin(headless=args.headless)
    from ads_core.extended import app
    import uvicorn

    if not args.headless:
        open_browser_after_start(args.port)
    print(f"LHM Ads AI đang chạy trên http://127.0.0.1:{args.port}/studio")
    print("Chỉ máy này truy cập được. Nhấn Ctrl+C để dừng.")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", workers=1)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        sys.exit(1)
