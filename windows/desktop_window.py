"""Native Windows desktop shell for the local LHM Ads AI dashboard.

Uses Microsoft Edge WebView2 through pywebview: a standalone resizable Windows
application window, *not* a Chrome/Edge browser tab. Backend and encrypted
database remain on 127.0.0.1 on the user's own PC. OAuth consent is explicitly
opened in the system browser because Google's policy forbids embedded login.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


class DesktopBridge:
    """Tiny allowlisted bridge, with no Ads tokens, file access or remote code."""

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
    try:
        wait_for_service(port, thread)
        import webview
        url = f'http://localhost:{port}' + (
            '/setup#token=' + setup_token if setup_token else '/studio'
        )
        window = webview.create_window(
            'LHM Ads AI · Advertising Studio',
            url=url,
            js_api=DesktopBridge(),
            width=1440, height=910,
            min_size=(1020, 680), resizable=True,
            background_color='#f3e8df',
            confirm_close=False,
        )
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
