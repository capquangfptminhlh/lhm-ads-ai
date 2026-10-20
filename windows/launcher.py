"""LHM Ads AI local Windows launcher: windowed app, browser onboarding, no MCP."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import urllib.request

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def data_directory() -> Path:
    override = os.environ.get('LHM_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get('LOCALAPPDATA')
    return Path(local) / 'LHMAdsAI' if local else Path.home() / '.lhm-ads-ai'


def configure_local_storage() -> Path:
    folder = data_directory()
    folder.mkdir(parents=True, exist_ok=True)
    settings_file = folder / 'local-settings.json'
    if settings_file.exists():
        config = json.loads(settings_file.read_text(encoding='utf-8'))
    else:
        config = {
            'MASTER_KEY': base64.b64encode(secrets.token_bytes(32)).decode('ascii'),
            'SESSION_SECRET': secrets.token_urlsafe(48),
        }
        fd = os.open(settings_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(config, fh)
    for name in ('MASTER_KEY', 'SESSION_SECRET'):
        os.environ.setdefault(name, config[name])
    os.environ.setdefault('DB_PATH', str(folder / 'data' / 'lhm-ads.sqlite3'))
    os.environ['COOKIE_SECURE'] = 'false'
    return folder


def configure_windowed_logs(folder: Path):
    """PyInstaller --windowed sets stdout/stderr to None. Never use a console window."""
    if getattr(sys, 'frozen', False) and (sys.stdout is None or sys.stderr is None):
        logs = folder / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        # Stored only on this PC for startup troubleshooting.
        stream = open(logs / 'startup.log', 'a', encoding='utf-8', buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')


def show_startup_error(message: str):
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, message, 'LHM Ads AI - Không thể khởi động', 0x10
            )
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description='LHM Ads AI - Windows desktop')
    p.add_argument('--headless', action='store_true', help='CI only; do not open GUI')
    p.add_argument('--window-smoke', action='store_true', help='Short native-window test on Windows')
    p.add_argument('--port', type=int, default=8765, help='Local-only port')
    args = p.parse_args()
    if not 1024 <= args.port <= 65535:
        p.error('Port must be 1024..65535')
    os.environ['LHM_DESKTOP_MODE'] = '1'
    os.environ['PUBLIC_BASE_URL'] = f'http://localhost:{args.port}'
    folder = configure_local_storage()
    configure_windowed_logs(folder)
    from ads_core.desktop_onboarding import prepare_first_run
    setup_token = prepare_first_run()
    # Import routes after the onboarding token is created.
    from ads_core.extended import app
    import uvicorn
    if args.headless:
        # CI tests the local HTTP API without opening a desktop window.
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning', workers=1)
    else:
        from windows.desktop_window import run_window
        run_window(app, port=args.port, setup_token=setup_token,
                   data_folder=folder, smoke_window=args.window_smoke)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        # Don't reveal exception internals/API keys to the user.
        import traceback
        if sys.stderr is not None:
            traceback.print_exc(file=sys.stderr)
        show_startup_error(
            'Ứng dụng chưa khởi động được. Kiểm tra cổng 8765 và mở lại LHM Ads AI. '
            'Nếu vẫn lỗi, xem thư mục logs trong LHMAdsAI tại AppData của Windows.'
        )
        sys.exit(1)
