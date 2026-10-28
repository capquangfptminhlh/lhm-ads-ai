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


# A browser callback cannot close an Edge/Chrome tab that it did not open.
# Keep a process-local reference to the already running native WebView2 window
# so its own loopback OAuth return page can bring the app to the foreground.
_native_window = None
_focus_reset_timer = None
_focus_lock = threading.Lock()


def focus_native_window() -> bool:
    global _focus_reset_timer
    with _focus_lock:
        window = _native_window
        if window is None:
            return False
        try:
            # pywebview supports an on_top property; toggling it briefly raises
            # the existing app without changing the user's permanent preference.
            window.show()
            window.on_top = True
            if _focus_reset_timer is not None:
                _focus_reset_timer.cancel()
            def reset_on_top():
                with _focus_lock:
                    if _native_window is window:
                        try:
                            window.on_top = False
                        except (AttributeError, OSError, RuntimeError):
                            pass
            timer = threading.Timer(1.0, reset_on_top)
            timer.daemon = True
            _focus_reset_timer = timer
            timer.start()
            return True
        except (AttributeError, OSError, RuntimeError):
            return False


class DesktopBridge:
    """Native-only bridge: allowlisted OAuth and cryptographically verified updates."""

    def __init__(self, data_folder: Path | None = None, executable: Path | None = None):
        self.data_folder = data_folder
        self.executable = executable
        self.install_requested = False
        self.window = None
        self.native_license_proof = None

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

    def get_local_license_proof(self) -> str:
        """Only a per-process local proof to authorize trusted WebView requests."""
        return self.native_license_proof or ''

    def open_license_url(self, url: str) -> bool:
        """Open ONLY the first-party short-lived pairing page or the plan/renewal
        page, never remote scripts."""
        from urllib.parse import urlsplit, parse_qs
        from uuid import UUID
        if url == 'https://ads.lhmcrm.com/local/':
            return bool(webbrowser.open(url, new=1))
        try:
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or parsed.netloc != 'ads.lhmcrm.com' or parsed.path != '/desktop/pair/':
                return False
            values = parse_qs(parsed.query)
            if set(values) != {'id'} or len(values['id']) != 1 or parsed.fragment:
                return False
            if str(UUID(values['id'][0], version=4)) != values['id'][0].lower():
                return False
        except (ValueError, TypeError, KeyError):
            return False
        return bool(webbrowser.open(url, new=1))

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
               smoke_window: bool = False, native_license_proof: str | None = None):
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
    bridge.native_license_proof = native_license_proof
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
        global _native_window
        _native_window = window
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
        global _focus_reset_timer
        with _focus_lock:
            _native_window = None
            if _focus_reset_timer is not None:
                _focus_reset_timer.cancel()
                _focus_reset_timer = None
        server.should_exit = True
        thread.join(timeout=8)
