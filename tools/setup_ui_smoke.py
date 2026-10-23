"""Real Chromium first-run walkthrough, before any account exists.

Uses a temporary local SQLite database and a per-test ephemeral setup token;
never touches real customer data, provider tokens or remote Ads APIs.
"""
import base64
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'artifacts'/'ui-preview'
PORT=18799
BASE=f'http://127.0.0.1:{PORT}'


def wait_ready(proc):
    for _ in range(120):
        if proc.poll() is not None:
            raise RuntimeError('Fresh desktop startup exited early')
        try:
            with urllib.request.urlopen(BASE+'/healthz', timeout=2) as response:
                if response.status==200:
                    return
        except Exception:
            time.sleep(.25)
    raise RuntimeError('No local FastAPI health response')


def main():
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lhm-setup-ui-') as workspace:
        wd=Path(workspace)
        tokenfile=wd/'test-ephemeral-setup-token.txt'
        env=os.environ.copy()
        env.update({
            'DB_PATH':str(wd/'first-run.sqlite3'),
            'MASTER_KEY':base64.b64encode(secrets.token_bytes(32)).decode(),
            'SESSION_SECRET':secrets.token_urlsafe(48),
            'COOKIE_SECURE':'false','LHM_DESKTOP_MODE':'1',
            'PUBLIC_BASE_URL':BASE,
            'LHM_UI_TEST_TOKEN_PATH':str(tokenfile),
            'PYTHONPATH':str(ROOT),
        })
        # Generate token in the same process that handles /api/desktop/first-run.
        code=(
            "import os;from pathlib import Path;"
            "from ads_core.desktop_onboarding import prepare_first_run;"
            "token=prepare_first_run();"
            "Path(os.environ['LHM_UI_TEST_TOKEN_PATH']).write_text(token,encoding='ascii');"
            "import uvicorn;uvicorn.run('ads_core.extended:app',"
            f"host='127.0.0.1',port={PORT},log_level='error')"
        )
        proc=subprocess.Popen([sys.executable,'-c',code],cwd=str(ROOT),env=env)
        try:
            wait_ready(proc)
            for _ in range(60):
                if tokenfile.is_file():
                    break
                time.sleep(.1)
            if not tokenfile.is_file():
                raise RuntimeError('Ephemeral first-run token absent')
            token=tokenfile.read_text(encoding='ascii')
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1440,'height':940},
                                      device_scale_factor=1)
                page.goto(BASE+'/setup#token='+token,wait_until='networkidle')
                expect(page.locator('#setup-form')).to_be_visible()
                expect(page.locator('#submit')).to_be_enabled()
                assert page.evaluate("""() => {
                    const color=getComputedStyle(document.querySelector('.setup-card')).backgroundColor;
                    return color==='rgb(23, 24, 28)';
                }"""),'First run must share Studio dark surface'
                assert page.locator('link[href="/static/setup-dark.css"]').count()==1
                expect(page.locator('.preview-head')).to_contain_text('CHƯA CÓ DỮ LIỆU ADS')
                expect(page.locator('.intro')).to_contain_text('Dashboard đen')
                assert page.evaluate("""() => {
                    const rect=document.querySelector('.app-frame').getBoundingClientRect();
                    return Math.abs(rect.left)<=1 &&
                        Math.abs(rect.width-window.innerWidth)<=1 &&
                        document.documentElement.scrollWidth<=window.innerWidth+1 &&
                        document.documentElement.scrollHeight<=window.innerHeight+2;
                }"""), 'Desktop setup should fit 1440x940 without unnecessary page scrolling'
                page.screenshot(path=str(ARTIFACTS/'16-desktop-first-run-dark.png'),
                                full_page=True)
                page.set_viewport_size({'width':1024,'height':768})
                expect(page.locator('.aside-card')).to_be_hidden()
                expect(page.locator('#submit')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
                page.screenshot(path=str(ARTIFACTS/'18-compact-desktop-first-run.png'),
                                full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('#email')).to_be_visible()
                expect(page.locator('#submit')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
                page.screenshot(path=str(ARTIFACTS/'17-mobile-first-run-dark.png'),
                                full_page=True)
                # End-to-end: local setup token, CSRF-safe first admin and dark Studio.
                page.locator('#email').fill('owner@setup.test')
                page.locator('#password').fill('UniqueStrongPassword!2026')
                page.locator('#confirm').fill('UniqueStrongPassword!2026')
                page.locator('#submit').click()
                page.wait_for_url(BASE+'/studio',timeout=12000)
                expect(page.locator('#shell')).to_be_visible(timeout=12000)
                assert page.locator('link[href="/static/finpoint-theme.css"]').count()==1
                print('PASS: dark Windows first-run at desktop/mobile, no horizontal overflow')
                print('PASS: owner account securely initialized and redirected to dark Studio')
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__=='__main__':
    main()
