"""Browser-level smoke test of the real LHM Ads AI provider UI.

Starts the actual local FastAPI app with a fresh throwaway SQLite database,
logs in through the UI, switches Google/Meta flows, creates a labeled demo
account and verifies provider-scoped filtering. NO real Ads API is called.
Screenshots are produced by Chromium rather than a design generator.
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

BASE = 'http://127.0.0.1:18798'
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / 'artifacts' / 'ui-preview'
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def wait_ready(proc):
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError('FastAPI exited before starting')
        try:
            with urllib.request.urlopen(BASE + '/healthz', timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(.25)
    raise RuntimeError('FastAPI health did not become ready')


def main():
    with tempfile.TemporaryDirectory(prefix='lhm-ui-') as scratch:
        env = os.environ.copy()
        env.update({
            'DB_PATH': str(Path(scratch) / 'lhm-ui.sqlite3'),
            'MASTER_KEY': base64.b64encode(secrets.token_bytes(32)).decode(),
            'SESSION_SECRET': secrets.token_urlsafe(48),
            'COOKIE_SECURE':'false',
            'LHM_DESKTOP_MODE':'1',
            'PUBLIC_BASE_URL':BASE,
        })
        # Create test admin in an isolated local database, not in real user data.
        os.environ.update({k:env[k] for k in ('DB_PATH','MASTER_KEY','SESSION_SECRET','COOKIE_SECURE','LHM_DESKTOP_MODE','PUBLIC_BASE_URL')})
        from ads_core.db import init_db, connection
        from ads_core.security import hash_password
        init_db()
        with connection() as db:
            db.execute(
                'INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)',
                ('preview@example.test',hash_password('preview_password_123!'),'preview','admin'))
        proc = subprocess.Popen(
            [sys.executable,'-m','uvicorn','ads_core.extended:app','--host','127.0.0.1','--port','18798',
             '--log-level','warning'],
            cwd=str(ROOT), env=env,
        )
        try:
            wait_ready(proc)
            with sync_playwright() as play:
                browser=play.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1440,'height':940},device_scale_factor=1)
                page.goto(BASE+'/studio',wait_until='networkidle')
                page.locator('#login-email').fill('preview@example.test')
                page.locator('#login-pass').fill('preview_password_123!')
                page.locator('#login-form button[type=submit]').click()
                page.locator('#shell').wait_for(state='visible')
                page.locator('button[data-page=accounts]').click()
                page.locator('[data-provider-choice=google]').wait_for(state='visible')
                assert page.locator('[data-provider-detail=google]').is_visible()
                assert not page.locator('[data-provider-detail=meta]').is_visible()
                page.evaluate('window.scrollTo(0, 0)')
                page.wait_for_timeout(850)  # Let transitions finish before capture
                page.screenshot(path=str(ARTIFACTS/'01-google-provider.png'),full_page=True)
                page.locator('[data-provider-choice=meta]').click()
                assert page.locator('[data-provider-detail=meta]').is_visible()
                assert not page.locator('[data-provider-detail=google]').is_visible()
                assert page.locator('[data-provider-choice=meta]').get_attribute('aria-pressed')=='true'
                page.evaluate('window.scrollTo(0, 0)')
                page.wait_for_timeout(850)  # Let transitions finish before capture
                page.screenshot(path=str(ARTIFACTS/'02-meta-provider.png'),full_page=True)

                # Test the real local API through the GUI. Demo is separated.
                page.locator('#add-account').click()
                page.locator('#account-dialog').wait_for(state='visible')
                page.locator('#account-form input[name=label]').fill('Preview Demo Only')
                page.locator('#account-form input[name=external_id]').fill('preview_demo_1')
                page.locator('#manual-submit').click()
                page.locator('#account-dialog').wait_for(state='hidden')
                page.locator('[data-account-filter=demo]').click()
                row=page.locator('#accounts-table tr[data-platform=demo]')
                row.wait_for(state='visible')
                assert 'Preview Demo Only' in row.inner_text()
                page.locator('[data-account-filter=google]').click()
                assert not row.is_visible()
                page.locator('[data-account-filter=meta]').click()
                assert not row.is_visible()
                page.locator('[data-account-filter=demo]').click()
                assert row.is_visible()
                page.evaluate('window.scrollTo(0, 0)')
                page.wait_for_timeout(850)  # Let transitions finish before capture
                page.locator('#fp-accounts-all').wait_for(state='visible')
                assert page.locator('#fp-accounts-all').inner_text() == '1'
                assert page.locator('#fp-accounts-google').inner_text() == '0'
                assert page.locator('#fp-accounts-meta').inner_text() == '0'
                page.locator('button[data-page=assistant]').click()
                page.locator('#fp-ai-mode').wait_for(state='visible')
                expect(page.locator('#fp-ai-mode')).to_have_text('Phân tích nội bộ', timeout=12000)
                page.locator('[data-fp-prompt]').first.click()
                assert 'Phân tích hiệu suất' in page.locator('#chat-input').input_value()
                # Choosing an AI template only fills the text field; it never sends an API request.
                page.wait_for_timeout(500)
                page.screenshot(path=str(ARTIFACTS/'09-finpoint-ai-center.png'),full_page=True)
                page.locator('button[data-page=accounts]').click()
                page.locator('#accounts-table tr[data-platform=demo]').wait_for(state='visible')
                page.screenshot(path=str(ARTIFACTS/'03-demo-filter.png'),full_page=True)
                # Regression smoke: independent FinPoint workspace pages.
                for name, marker in [
                    ('campaigns', '#opt-inspect'),
                    ('autopilot', '#ap-panel'),
                    ('alerts', '#advisor-list'),
                    ('license', '#license-device'),
                    ('reports', '#ws-report-table')]:
                    page.locator(f'button[data-page={name}]').click()
                    page.locator(f'#page-{name}').wait_for(state='visible')
                    page.locator(marker).wait_for(state='visible')
                    assert page.locator('#page-approvals').is_hidden(), name
                page.locator('#ws-report-chart').wait_for(state='visible')
                page.wait_for_timeout(500)
                assert 'Preview Demo Only' in page.locator('#ws-report-table').inner_text()
                assert 'DEMO' in page.locator('#ws-report-table').inner_text()
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'04-finpoint-reports.png'),full_page=True)
                page.locator('button[data-page=autopilot]').click()
                page.locator('#ap-panel').wait_for(state='visible')
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'05-finpoint-autopilot.png'),full_page=True)
                page.locator('button[data-page=alerts]').click()
                page.locator('#advisor-list').wait_for(state='visible')
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'06-finpoint-alerts.png'),full_page=True)
                page.locator('button[data-page=license]').click()
                page.locator('#license-device').wait_for(state='visible')
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'07-finpoint-license.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                page.locator('#menu').click()
                page.locator('button[data-page=reports]').click()
                page.locator('#page-reports').wait_for(state='visible')
                page.wait_for_timeout(400)
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'08-finpoint-mobile-reports.png'),full_page=True)
                print('PASS: separate campaigns, autopilot, alerts, license and reports pages; report data is sourced from Demo API')
                print('PASS: Google/Meta selected separately, Demo not mixed, native API/UI flow works')
                browser.close()
        finally:
            proc.terminate()
            try: proc.wait(timeout=8)
            except subprocess.TimeoutExpired: proc.kill()


if __name__=='__main__':
    main()
