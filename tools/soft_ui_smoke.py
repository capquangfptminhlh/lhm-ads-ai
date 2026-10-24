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
                desktop.locator('#login .lhm-soft-eye').evaluate('(el) => el.click()')
                assert desktop.locator('#login #login-pass').get_attribute('type')=='password'
                check_no_horizontal_overflow(desktop)
                desktop.screenshot(path=str(OUTPUT/'lhm-soft-login-desktop.png'),full_page=True)
                desktop.close()

                # Public landing is a real marketing page. The PWA is inaccessible
                # until the customer unlocks the encrypted local device vault.
                site=browser.new_page(viewport={'width':1440,'height':900})
                errors=[]
                site.on('pageerror',lambda error:errors.append(str(error)))
                site.goto(origin+'/',wait_until='domcontentloaded')
                site.locator('.mk-nav-login').wait_for()
                assert 'Quản lý quảng cáo' in site.locator('h1').first.inner_text()
                assert 'lhmcrm.com' in site.locator('link[rel="canonical"]').get_attribute('href')
                check_no_horizontal_overflow(site)
                site.screenshot(path=str(OUTPUT/'lhm-public-marketing-desktop.png'),full_page=True)
                site.locator('.mk-nav-login').click()
                site.wait_for_url('**/local/', timeout=10000)
                assert site.url.endswith('/local/')
                site.locator('#pwa-access-gate').wait_for()
                site.locator('#lhm-vault-password').wait_for()
                assert site.locator('body.pwa-gated').count()==1
                assert not site.locator('.pwa-sidebar').is_visible()
                assert not site.locator('.pwa-page[data-view="dashboard"]').is_visible()
                assert site.locator('#pwa-access-gate').get_by_text('không phải tài khoản Cloud',exact=False).count()>=1
                site.screenshot(path=str(OUTPUT/'lhm-pwa-login-desktop.png'),full_page=True)
                password='Demo-vault-2026-strong-passphrase!'
                site.locator('#lhm-vault-password').fill(password)
                site.locator('#lhm-vault-access-action').click()
                site.locator('body.lhm-pwa:not(.pwa-gated)').wait_for(timeout=15000)
                assert site.locator('.pwa-page.active[data-view="dashboard"]').is_visible()
                assert site.locator('.pwa-sidebar').is_visible()
                site.screenshot(path=str(OUTPUT/'lhm-independent-studio-desktop.png'),full_page=True)
                site.locator('#pwa-signout').click()
                site.locator('body.pwa-gated').wait_for(timeout=10000)
                assert not site.locator('.pwa-sidebar').is_visible()
                assert site.locator('#lhm-vault-access-action').inner_text()=='Mở khóa kho'
                site.locator('#lhm-vault-password').fill(password)
                site.locator('#lhm-vault-access-action').click()
                site.locator('body.lhm-pwa:not(.pwa-gated)').wait_for(timeout=15000)
                assert site.locator('#pwa-overview-accounts').inner_text()=='0'
                assert not errors,errors
                site.close()

                mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
                mobile_errors=[]
                mobile.on('pageerror',lambda error:mobile_errors.append(str(error)))
                mobile.goto(origin+'/',wait_until='domcontentloaded')
                mobile.locator('.mk-nav-login').wait_for()
                check_no_horizontal_overflow(mobile)
                mobile.screenshot(path=str(OUTPUT/'lhm-public-marketing-mobile.png'),full_page=True)
                mobile.locator('.mk-nav-login').click()
                mobile.wait_for_url('**/local/', timeout=10000)
                mobile.locator('#pwa-access-gate').wait_for()
                assert not mobile.locator('.pwa-mobile-dock').is_visible()
                check_no_horizontal_overflow(mobile)
                mobile.screenshot(path=str(OUTPUT/'lhm-pwa-login-mobile.png'),full_page=True)
                mobile.locator('#lhm-vault-password').fill(password)
                mobile.locator('#lhm-vault-access-action').click()
                mobile.locator('body.lhm-pwa:not(.pwa-gated)').wait_for(timeout=15000)
                assert mobile.locator('.pwa-mobile-dock').is_visible()
                assert mobile.locator('.pwa-page.active[data-view="dashboard"]').is_visible()
                mobile.screenshot(path=str(OUTPUT/'lhm-studio-pwa-dashboard-mobile.png'),full_page=True)
                mobile.locator('.pwa-mobile-dock [data-go="accounts"]').click()
                mobile.locator('#lhm-vault-unlocked:not(.hidden)').wait_for()
                mobile.locator('#lhm-vault-platform').select_option('google')
                mobile.locator('#lhm-vault-account').fill('111-222-3333')
                mobile.locator('#lhm-vault-label').fill('Tài khoản minh họa')
                mobile.locator('#lhm-vault-add button[type="submit"]').click()
                mobile.wait_for_function("window.LHMDeviceVault.listAccounts().length === 1")
                mobile.locator('.pwa-mobile-dock [data-go="dashboard"]').click()
                assert mobile.locator('#pwa-overview-accounts').inner_text()=='1'
                mobile.locator('#pwa-account-preview').get_by_text('Tài khoản minh họa').wait_for()
                check_no_horizontal_overflow(mobile)
                mobile.screenshot(path=str(OUTPUT/'lhm-studio-unlocked-mobile.png'),full_page=True)
                mobile.locator('#pwa-signout').click()
                mobile.locator('body.pwa-gated').wait_for(timeout=10000)
                assert not mobile.locator('.pwa-mobile-dock').is_visible()
                assert not mobile.locator('.pwa-page[data-view="dashboard"]').is_visible()
                mobile.locator('#lhm-vault-password').fill(password)
                mobile.locator('#lhm-vault-access-action').click()
                mobile.locator('body.lhm-pwa:not(.pwa-gated)').wait_for(timeout=15000)
                assert mobile.locator('#pwa-overview-accounts').inner_text()=='1'
                assert not mobile_errors,mobile_errors
                mobile.close()

                reduced=browser.new_page(viewport={'width':390,'height':844},
                  reduced_motion='reduce')
                reduced.goto(origin+'/local/',wait_until='domcontentloaded')
                reduced.locator('#pwa-access-gate').wait_for()
                anim=reduced.locator('.pwa-access-panel').evaluate(
                  "el=>getComputedStyle(el).animationDuration")
                assert anim in ('0s','0.00001s','1e-05s'),anim
                check_no_horizontal_overflow(reduced)
                reduced.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            os.chdir(old)
    print("PASS: marketing landing, password-gated PWA, sign out, encrypted vault, responsive screenshots,"
          " reduced motion, responsive overflow; screenshots in artifacts/ui-preview")

if __name__=='__main__': main()
