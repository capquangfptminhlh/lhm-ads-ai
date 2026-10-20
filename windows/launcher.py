"""LHM Ads AI Windows desktop entry point.

Runs the existing private web dashboard on the local machine ONLY. No MCP
connection, no listener on public/LAN interfaces, no shipping API credentials.
"""
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

# Allow source-mode execution from the repository; PyInstaller provides its own bundle path.
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
    """Generate a persistent encryption key only on first use, per Windows user."""
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
        # Atomic creation; no world-readable secrets in printed logs.
        fd = os.open(settings_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(config, fh)
    for name in ("MASTER_KEY", "SESSION_SECRET"):
        if not os.environ.get(name):
            os.environ[name] = config[name]
    os.environ.setdefault("DB_PATH", str(folder / "data" / "lhm-ads.sqlite3"))
    # For loopback HTTP only. Do NOT change to false for a public deployment.
    os.environ["COOKIE_SECURE"] = "false"
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
    print("\nFIRST RUN - Create the local administrator account")
    while True:
        email = input("Admin email: ").strip().lower()
        if "@" in email and "." in email.split("@")[-1]:
            break
        print("Invalid email. Try again.")
    while True:
        password = getpass.getpass("Password (minimum 12 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password == confirm and len(password) >= 12:
            break
        print("Passwords do not match or are too short.")
    with connection() as db:
        db.execute("INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)",
                   (email, hash_password(password), "main", "admin"))
    print("Local admin account created.")


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
        print("Open the dashboard manually:", url)

    threading.Thread(target=worker, name="open-dashboard", daemon=True).start()


def main() -> None:
    p = argparse.ArgumentParser(description="LHM Ads AI - run the local dashboard on Windows")
    p.add_argument("--headless", action="store_true", help="Skip admin setup and browser (CI mode)")
    p.add_argument("--port", type=int, default=8765, help="Localhost port (default 8765)")
    args = p.parse_args()
    if not (1024 <= args.port <= 65535):
        p.error("Port must be between 1024 and 65535")
    os.environ.setdefault("PUBLIC_BASE_URL", f"http://127.0.0.1:{args.port}")
    configure_local_storage()
    bootstrap_first_admin(headless=args.headless)
    from ads_core.extended import app
    import uvicorn

    if not args.headless:
        open_browser_after_start(args.port)
    print(f"LHM Ads AI listening on http://127.0.0.1:{args.port}/studio")
    print("Local access only. Press Ctrl+C to stop.")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", workers=1)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        sys.exit(1)
