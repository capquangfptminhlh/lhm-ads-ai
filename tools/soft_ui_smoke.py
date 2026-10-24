"""Verify redesigned soft-depth UI in real Chromium at desktop/mobile widths.

Screenshots contain only synthetic demo credentials/accounts, never customers.
Cloudflare bundle is built and served locally, no remote app or Ads auth required.
"""
from __future__ import annotations
import os
import http.server
import socketserver
import tempfile
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from tools.build_github_pages import build

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"artifacts"/"ui-preview"

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*_args):pass

class Server(socketserver.ThreadingMixIn,http.server.HTTPServer):
    daemon_threads=True
    allow_reuse_address=True

def check_no_horizontal_overflow(page):
    result=page.evaluate("""() => ({
        body:document.body.scrollWidth,viewport:document.documentElement.clientWidth
    })""")
    assert result['body']<=result['viewport']+2, result

def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        folder=build(Path(temp)/'app')
        old=os.getcwd()
        os.chdir(folder)
        server=Server(('127.0.0.1',0),Quiet)
        th=threading.Thread(target=server.serve_forever,daemon=True)
        th.start()
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                origin=f'http://127.0.0.1:{server.server_address[1]}'
                desktop=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
                desktop.goto(origin+'/studio/',wait_until='domcontentloaded')
                desktop.locator('#login .login-box').wait_for()
                desktop.wait_for_timeout(750)
                assert desktop.locator('link[href="/static/soft-motion-ui.css"]').count()==1
                assert desktop.locator('#lhm-static-api-guard').count()==1
                assert desktop.locator('#login .lhm-soft-local-link').count()==1
                assert desktop.locator('#login .lhm-soft-eye').count()==1
                assert desktop.locator('#login #login-pass').get_attribute('type')=='password'
                desktop.locator('#login .lhm-soft-eye').evaluate('(el) => el.click()')
                assert desktop.locator('#login #login-pass').get_attribute('type')=='text'
                desktop.locator('#login .lhm-soft-eye').click(force=True)
                assert desktop.locator('#login #login-pass').get_attribute('type')=='password'
                check_no_horizontal_overflow(desktop)
                desktop.screenshot(path=str(OUTPUT/'lhm-soft-login-desktop.png'),full_page=True)
                desktop.close()

                mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
                mobile.goto(origin+'/local/',wait_until='domcontentloaded')
                mobile.locator('#device-only-vault').wait_for()
                mobile.wait_for_timeout(750)
                assert mobile.locator('link[href="/static/soft-motion-ui.css"]').count()==1
                assert mobile.locator('#lhm-vault-access-action').count()==1
                check_no_horizontal_overflow(mobile)
                mobile.screenshot(path=str(OUTPUT/'lhm-soft-pwa-locked-mobile.png'),full_page=True)
                mobile.locator('#lhm-vault-password').fill('Demo-vault-2026-strong-passphrase!')
                mobile.locator('#lhm-vault-access-action').click()
                mobile.locator('#lhm-vault-unlocked:not(.hidden)').wait_for(timeout=15000)
                mobile.locator('#lhm-vault-platform').select_option('google')
                mobile.locator('#lhm-vault-account').fill('111-222-3333')
                mobile.locator('#lhm-vault-label').fill('Tài khoản minh họa')
                mobile.locator('#lhm-vault-add button[type="submit"]').click()
                mobile.wait_for_function("window.LHMDeviceVault.listAccounts().length === 1")
                mobile.wait_for_timeout(450)
                check_no_horizontal_overflow(mobile)
                mobile.screenshot(path=str(OUTPUT/'lhm-soft-pwa-unlocked-mobile.png'),full_page=True)
                mobile.close()

                reduced=browser.new_page(viewport={'width':390,'height':844},
                  reduced_motion='reduce')
                reduced.goto(origin+'/local/',wait_until='domcontentloaded')
                reduced.locator('#device-only-vault').wait_for()
                anim=reduced.locator('#device-only-vault').evaluate(
                  "el=>getComputedStyle(el).animationDuration")
                assert anim in ('0s','0.00001s','1e-05s'),anim
                check_no_horizontal_overflow(reduced)
                reduced.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            os.chdir(old)
    print("PASS: soft-depth desktop auth & mobile PWA animation, password toggle,"
          " reduced motion, responsive overflow; screenshots in artifacts/ui-preview")

if __name__=='__main__': main()
