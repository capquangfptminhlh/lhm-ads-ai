"""Native Windows desktop shell for the local LHM Ads AI dashboard.

Uses Microsoft Edge WebView2 through pywebview: a standalone resizable Windows
application window, *not* a Chrome/Edge browser tab. Backend and encrypted
database remain on 127.0.0.1 on the user's own PC. OAuth consent is explicitly
opened in the system browser because Google's policy forbids embedded login.
"""
from __future__ import annotations

import re
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


class DesktopBridge:
    """Native-only bridge: allowlisted OAuth and cryptographically verified updates."""

    def __init__(self, data_folder: Path | None = None, executable: Path | None = None):
        self.data_folder = data_folder
        self.executable = executable
        self.install_requested = False
        self.window = None

    def _can_update(self) -> bool:
        return (self.data_folder is not None and self.executable is not None
                and getattr(sys, 'frozen', False) and sys.platform == 'win32')

    def check_update(self) -> dict:
        if not self._can_update():
            return {'status': 'not_configured',
                    'message': 'Cập nhật online chỉ hỗ trợ bản EXE Windows.'}
        from windows.online_update import check
        return check()

    def download_update(self) -> dict:
        if not self._can_update():
            return {'status': 'not_configured',
                    'message': 'Cập nhật online chỉ hỗ trợ bản EXE Windows.'}
        from windows.online_update import download
        return download(self.data_folder)

    def install_update(self) -> dict:
        if not self._can_update() or self.install_requested:
            return {'status': 'invalid', 'message': 'Không thể bắt đầu cập nhật.'}
        from windows.online_update import staged_update
        if staged_update(self.data_folder) is None or self.window is None:
            return {'status': 'invalid', 'message': 'Chưa có bản cập nhật được xác minh.'}
        # Start the helper BEFORE closing the UI, so failure to start it
        # can be reported to the user while the running EXE is still safe.
        # The helper waits for this process to exit before touching the EXE.
        from windows.update_install import spawn_install_after_exit
        try:
            spawn_install_after_exit(self.data_folder, self.executable)
        except (OSError, RuntimeError, ValueError):
            return {'status': 'invalid',
                    'message': 'Không chạy được bộ cập nhật trên Windows. Phần mềm vẫn hoạt động.'}
        self.install_requested = True
        threading.Thread(target=self.window.destroy, daemon=True).start()
        return {'status': 'restarting', 'message': 'Đang đóng để cài đặt bản mới.'}

    def open_oauth_url(self, url: str) -> bool:
        from urllib.parse import urlsplit
        if not isinstance(url, str) or len(url) > 4096:
            return False
        parsed = urlsplit(url)
        google = (parsed.scheme == 'https' and parsed.netloc == 'accounts.google.com'
                  and parsed.path == '/o/oauth2/v2/auth')
        facebook = (parsed.scheme == 'https' and parsed.netloc == 'www.facebook.com'
                    and re.fullmatch(r'/v\d+\.\d+/dialog/oauth', parsed.path) is not None)
        if not (google or facebook):
            return False
        return bool(webbrowser.open(url, new=1))


def wait_for_service(port: int, thread: threading.Thread, *, timeout: float = 30):
    health = f'http://127.0.0.1:{port}/healthz'
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if not thread.is_alive():
            raise RuntimeError('Máy chủ dữ liệu cục bộ không khởi động được.')
        try:
            with urllib.request.urlopen(health, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError('Không thể khởi động dữ liệu cục bộ. Cổng đang bận hoặc bị chặn.')


def run_window(app, *, port: int, setup_token: str | None, data_folder: Path,
               smoke_window: bool = False):
    import uvicorn
    # The local API is a private implementation detail. The user sees only one
    # branded Windows window. Server lifetime follows GUI window lifetime.
    config = uvicorn.Config(
        app, host='127.0.0.1', port=port, workers=1,
        log_level='warning', access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name='lhm-local-api', daemon=True)
    thread.start()
    bridge = DesktopBridge(
        data_folder=data_folder,
        executable=Path(sys.executable) if getattr(sys, 'frozen', False) else None,
    )
    try:
        wait_for_service(port, thread)
        import webview
        url = f'http://localhost:{port}' + (
            '/setup#token=' + setup_token if setup_token else '/studio'
        )
        window = webview.create_window(
            'LHM Ads AI · Advertising Studio',
            url=url,
            js_api=bridge,
            # Open maximized on the current monitor, keeping the native
            # title bar and taskbar. Users can still restore/resize normally.
            maximized=True,
            width=1280, height=800,
            # Do not force a minimum larger than the available work area
            # on small/high-DPI Windows displays.
            min_size=(760, 540), resizable=True,
            background_color='#0b0c0e',
            confirm_close=False,
        )
        bridge.window = window
        if smoke_window:
            def close_after_start():
                time.sleep(8)
                try:
                    window.destroy()
                except Exception:
                    pass
            threading.Thread(
                target=close_after_start, name='gui-smoke-close', daemon=True
            ).start()
        # WebView2 Runtime is bundled with modern Edge/Windows, but older
        # systems may need it installed separately. Never silently degrade
        # to opening the user's browser: that would recreate the original UX.
        webview.start(
            gui='edgechromium',
            debug=False,
            private_mode=False,
            storage_path=str(data_folder / 'webview'),
        )
    finally:
        server.should_exit = True
        thread.join(timeout=8)
