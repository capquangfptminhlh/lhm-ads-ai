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
                # System-browser OAuth confirmation must be legible on dark
                # desktop and must guide customer back to the native window.
                finish=browser.new_page(viewport={'width':900,'height':700},device_scale_factor=1)
                finish.goto(BASE+'/oauth/finished?status=ready',wait_until='networkidle')
                expect(finish.locator('#result-title')).to_contain_text('Đã nhận quyền truy cập')
                expect(finish.locator('#oauth-finished-close')).to_be_visible()
                expect(finish.locator('#oauth-close-hint')).to_contain_text('Ctrl')
                assert finish.locator('h1').evaluate('el => getComputedStyle(el).color') == 'rgb(255, 255, 255)'
                assert finish.locator('body').evaluate('el => getComputedStyle(el).backgroundColor') == 'rgb(11, 14, 19)'
                finish.screenshot(path=str(ARTIFACTS/'22-oauth-complete-browser.png'))
                # The standalone browser test has no native window; a click
                # must show Alt+Tab instead of falsely claiming the tab closed.
                finish.locator('#oauth-finished-close').click()
                expect(finish.locator('#oauth-close-hint')).to_contain_text(
                    'Alt + Tab', timeout=7000)
                expect(finish.locator('#oauth-finished-close')).to_contain_text('Thử quay về phần mềm')
                finish.close()
                page=browser.new_page(viewport={'width':1440,'height':940},device_scale_factor=1)
                page.goto(BASE+'/studio',wait_until='networkidle')
                page.locator('#login-email').fill('preview@example.test')
                page.locator('#login-pass').fill('preview_password_123!')
                page.locator('#login-form button[type=submit]').click()
                page.locator('#shell').wait_for(state='visible')
                # Motion is progressive and never invents Ads totals.
                assert page.locator('link[href="/static/finpoint-motion.css"]').count() == 1
                assert page.locator('script[src="/static/finpoint-motion.js"]').count() == 1
                assert page.locator('#navigation button[data-page=dashboard]').get_attribute('aria-current') == 'page'
                # First run has NO connected Ads API: show actions, not fake figures.
                expect(page.locator('#dashboard-onboarding')).to_be_visible(timeout=12000)
                expect(page.locator('#dashboard-onboarding')).to_contain_text('Ủy quyền an toàn')
                assert page.locator('#k-spend').inner_text().strip() == '—'
                page.screenshot(path=str(ARTIFACTS/'12-first-run-onboarding.png'),full_page=True)
                # New command palette does not mutate ads or bypass role navigation.
                page.locator('#ui-command-open').click()
                expect(page.locator('#ui-command-overlay')).to_be_visible()
                expect(page.locator('#ui-command-open')).to_have_attribute('aria-expanded','true')
                expect(page.locator('#ui-command-input')).to_be_focused()
                page.locator('#ui-command-input').fill('phe duyet')
                expect(page.locator('#ui-command-results [data-page=approvals]')).to_be_visible()
                expect(page.locator('#ui-command-results [data-page=team]')).to_have_count(0)
                page.wait_for_timeout(380)  # Capture AFTER palette entrance animation finishes
                assert page.locator('.ui-command-dialog').evaluate('node => getComputedStyle(node).opacity') == '1'
                page.screenshot(path=str(ARTIFACTS/'13-command-palette-desktop.png'))
                page.locator('#ui-command-input').press('Enter')
                expect(page.locator('#page-approvals')).to_be_visible()
                expect(page.locator('#ui-command-overlay')).to_be_hidden()
                page.locator('#ui-command-open').click()
                page.locator('#ui-command-input').fill('nhat ky')
                expect(page.locator('#ui-command-results [data-page=audit]')).to_be_visible()
                page.keyboard.press('Escape')
                expect(page.locator('#ui-command-overlay')).to_be_hidden()
                expect(page.locator('#ui-command-open')).to_be_focused()
                # Original Ctrl+K account search remains intact.
                page.keyboard.press('Control+k')
                page.locator('#navigation button[data-page=accounts].active').wait_for(state='visible')
                expect(page.locator('#global-account-search')).to_be_focused(timeout=5000)
                assert page.locator('#navigation button[data-page=accounts]').get_attribute('aria-current') == 'page'
                page.locator('[data-provider-choice=google]').wait_for(state='visible')
                # Help is bundled locally for customers and opens inside Studio.
                page.locator('#page-accounts [data-customer-help=google]').click()
                expect(page.locator('#customer-help-dialog')).to_be_visible()
                expect(page.locator('#customer-help-content')).to_contain_text('Google Ads API')
                page.locator('[data-help-tab=meta]').click()
                expect(page.locator('#customer-help-content')).to_contain_text('Facebook / Meta Ads')
                page.locator('[data-help-tab=mcp]').click()
                expect(page.locator('#customer-help-content')).to_contain_text('chưa tích hợp MCP server trực tiếp')
                page.locator('[data-help-tab=errors]').click()
                expect(page.locator('#customer-help-content')).to_contain_text('access_denied')
                page.locator('[data-help-tab=google]').click()
                page.screenshot(path=str(ARTIFACTS/'21-customer-offline-help.png'))
                page.locator('#customer-help-start').click()
                expect(page.locator('#customer-help-dialog')).to_be_hidden()
                expect(page.locator('#provider-connect-guide')).to_be_visible()
                page.locator('#navigation button[data-page=dashboard]').click()
                page.locator('#page-dashboard').wait_for(state='visible')
                page.wait_for_timeout(1250)
                assert page.locator('#k-clicks').inner_text().strip()
                page.screenshot(path=str(ARTIFACTS/'10-finpoint-animated-overview.png'), full_page=True)
                page.locator('#navigation button[data-page=accounts]').click()
                page.locator('[data-provider-choice=google]').wait_for(state='visible')
                assert page.locator('[data-provider-detail=google]').is_visible()
                assert not page.locator('[data-provider-detail=meta]').is_visible()
                page.evaluate('window.scrollTo(0, 0)')
                page.wait_for_timeout(850)  # Let transitions finish before capture
                page.screenshot(path=str(ARTIFACTS/'01-google-provider.png'),full_page=True)

                # Regression for customer screenshot: an OAuth import option must
                # NEVER render light text on a white card in the dark Studio.
                page.evaluate("""() => {
                  const host=document.getElementById('oauth-pending-list');
                  const box=document.createElement('div');box.className='oauth-choice-box';
                  box.id='smoke-pending-import';
                  const heading=document.createElement('strong');heading.textContent='Chọn tài khoản Google Ads để thêm';
                  const list=document.createElement('div');list.className='oauth-choice-list';
                  const label=document.createElement('label');label.className='oauth-choice';
                  const cb=document.createElement('input');cb.type='checkbox';cb.checked=true;
                  const name=document.createElement('span');name.textContent='Tài khoản kiểm thử giao diện — VND';
                  label.append(cb,name);list.append(label);box.append(heading,list);host.append(box);
                }""")
                expect(page.locator('#smoke-pending-import')).to_be_visible()
                assert page.locator('#smoke-pending-import').evaluate("""box=>{
                  const text=box.querySelector('label span');
                  const fg=getComputedStyle(text).color;
                  const bg=getComputedStyle(box.querySelector('label')).backgroundColor;
                  return fg==='rgb(240, 241, 244)' && bg==='rgb(57, 48, 40)';
                }"""), 'OAuth account list text/background should be readable in dark mode'
                page.screenshot(path=str(ARTIFACTS/'23-oauth-selection-dark-contrast.png'))
                page.locator('#smoke-pending-import').evaluate('el => el.remove()')

                # Programmatic go() must trigger a real campaign account refresh,
                # not leave the dropdown permanently saying Đang tải tài khoản.
                page.evaluate("go('campaigns')")
                expect(page.locator('#opt-account')).not_to_contain_text('Đang tải tài khoản',timeout=15000)
                expect(page.locator('#opt-retry')).to_be_visible()
                page.screenshot(path=str(ARTIFACTS/'24-campaign-accounts-state.png'))
                page.locator('#navigation button[data-page=accounts]').click()
                page.locator('[data-provider-choice=meta]').click()
                assert page.locator('[data-provider-detail=meta]').is_visible()
                assert not page.locator('[data-provider-detail=google]').is_visible()
                assert page.locator('[data-provider-choice=meta]').get_attribute('aria-pressed')=='true'
                page.evaluate('window.scrollTo(0, 0)')
                page.wait_for_timeout(850)  # Let transitions finish before capture
                page.screenshot(path=str(ARTIFACTS/'02-meta-provider.png'),full_page=True)

                # Guided provider connection: from Account CTA to Settings, then
                # import Google Desktop OAuth JSON locally (dummy credentials).
                page.locator('[data-provider-settings=meta]').click()
                expect(page.locator('#page-settings')).to_be_visible()
                expect(page.locator('#provider-connect-guide')).to_be_visible()
                assert page.locator('[data-connect-provider=meta]').get_attribute('aria-pressed')=='true'
                expect(page.locator('#connection-guide-body')).to_contain_text('Redirect URI')
                # MCP mode is documentation-only, not an active LHM MCP endpoint.
                page.locator('[data-connection-mode=mcp]').click()
                expect(page.locator('#connection-guide-body')).to_contain_text('Meta Ads MCP')
                expect(page.locator('.connection-step-nav')).to_be_hidden()
                assert page.locator('[data-connection-mode=mcp]').get_attribute('aria-pressed')=='true'
                page.locator('[data-connect-provider=google]').click()
                expect(page.locator('#connection-guide-body')).to_contain_text('Google Ads MCP')
                page.locator('[data-connection-mode=api]').click()
                expect(page.locator('.connection-step-nav')).to_be_visible()
                expect(page.locator('#connection-guide-body')).to_contain_text('Google Cloud Console')
                page.screenshot(path=str(ARTIFACTS/'19-meta-guided-connection.png'),full_page=True)
                page.locator('[data-connect-provider=google]').click()
                expect(page.locator('#connection-guide-body')).to_contain_text('Google Cloud Console')
                page.locator('[data-connect-step="1"]').click()
                expect(page.locator('#connection-import-json')).to_be_visible()
                page.locator('#connection-json-file').set_input_files({
                    'name': 'fake-desktop-oauth.json',
                    'mimeType': 'application/json',
                    'buffer': b'{"installed":{"client_id":"12345678-testing.apps.googleusercontent.com","client_secret":"dummy-not-real"}}'
                })
                expect(page.locator('#desktop-google-id')).to_have_value('12345678-testing.apps.googleusercontent.com')
                expect(page.locator('#desktop-google-secret')).to_have_value('dummy-not-real')
                expect(page.locator('#connection-inline-message')).to_contain_text('Đã điền Client ID')
                # No automatic server submission until explicit Save.
                page.locator('[data-connect-step="2"]').click()
                page.locator('#connection-save').click()
                expect(page.locator('#connection-guide-status')).to_contain_text('Đã lưu ứng dụng',timeout=10000)
                page.locator('[data-connect-step="3"]').click()
                page.locator('#connection-open-oauth').click()
                expect(page.locator('#page-accounts')).to_be_visible()
                assert page.locator('[data-provider-choice=google]').get_attribute('aria-pressed')=='true'
                # Test compact responsive setup without leaking the dummy secret in screenshots.
                page.locator('[data-provider-settings=google]').click()
                page.locator('[data-connect-step="0"]').click()
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('#provider-connect-guide')).to_be_visible()
                overflow = page.evaluate("""() => ({
                    width: window.innerWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    elements: [...document.querySelectorAll('body *')].filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && (r.right > window.innerWidth + 2 || r.left < -2);
                    }).slice(0, 14).map(el => ({tag:el.tagName, id:el.id, cls:String(el.className).slice(0,70)}))
                })""")
                assert overflow['scrollWidth']<=overflow['width']+1, overflow
                page.screenshot(path=str(ARTIFACTS/'20-connection-guide-mobile.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':940})
                page.locator('#navigation button[data-page=accounts]').click()

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
                # In-list search and header search stay synchronized; no API search.
                page.locator('#account-list-search').fill('PREVIEW')
                expect(row).to_be_visible()
                expect(page.locator('#global-account-search')).to_have_value('PREVIEW')
                expect(page.locator('#account-search-status')).to_have_text('Hiển thị 1/1 tài khoản')
                page.locator('#account-list-search').fill('khong_co_tai_khoan')
                expect(row).to_be_hidden()
                expect(page.locator('#account-filter-empty')).to_be_visible()
                expect(page.locator('#account-search-status')).to_have_text('Hiển thị 0/1 tài khoản')
                page.locator('#account-list-search').fill('preview')
                expect(row).to_be_visible()
                expect(page.locator('#account-filter-empty')).to_be_hidden()
                page.locator('#global-account-search').fill('Preview')
                expect(page.locator('#account-list-search')).to_have_value('Preview')
                expect(row).to_be_visible()
                page.locator('#account-list-search').fill('')
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
                # Screenshot with explicitly labeled Demo source: showcase the orange
                # chart without inventing real client performance numbers.
                page.locator('#navigation button[data-page=dashboard]').click()
                page.locator('.fp-chart .trendline').wait_for(state='visible',timeout=12000)
                expect(page.locator('#source-warning')).to_contain_text('DỮ LIỆU DEMO',timeout=12000)
                expect(page.locator('#dashboard-onboarding')).to_be_visible()  # Demo is NOT live Ads
                page.wait_for_timeout(1800)
                page.screenshot(path=str(ARTIFACTS/'11-finpoint-orange-chart-demo.png'),full_page=True)
                page.locator('#navigation button[data-page=accounts]').click()
                page.locator('#navigation button[data-page=assistant]').click()
                page.locator('#fp-ai-mode').wait_for(state='visible')
                expect(page.locator('#fp-ai-mode')).to_have_text('Phân tích nội bộ', timeout=12000)
                page.locator('[data-fp-prompt]').first.click()
                assert 'Phân tích hiệu suất' in page.locator('#chat-input').input_value()
                # Choosing an AI template only fills the text field; it never sends an API request.
                page.wait_for_timeout(500)
                page.screenshot(path=str(ARTIFACTS/'09-finpoint-ai-center.png'),full_page=True)
                page.locator('#navigation button[data-page=accounts]').click()
                page.locator('#accounts-table tr[data-platform=demo]').wait_for(state='visible')
                page.screenshot(path=str(ARTIFACTS/'03-demo-filter.png'),full_page=True)
                # Essential workspace stays calm; advanced navigation opens
                # on demand and all existing features remain accessible.
                expect(page.locator('#nav-advanced')).not_to_have_attribute('open', '')
                page.locator('#nav-advanced > summary').click()
                expect(page.locator('#nav-advanced')).to_have_attribute('open','')
                page.screenshot(path=str(ARTIFACTS/'25-compact-sidebar-expanded.png'))
                # Regression smoke: independent FinPoint workspace pages.
                for name, marker in [
                    ('campaigns', '#opt-inspect'),
                    ('autopilot', '#ap-panel'),
                    ('alerts', '#advisor-list'),
                    ('license', '#license-device'),
                    ('reports', '#ws-report-table')]:
                    page.locator(f'#navigation button[data-page={name}]').click()
                    page.locator(f'#page-{name}').wait_for(state='visible')
                    page.locator(marker).wait_for(state='visible')
                    assert page.locator('#page-approvals').is_hidden(), name
                page.locator('#ws-report-chart').wait_for(state='visible')
                page.wait_for_timeout(500)
                assert 'Preview Demo Only' in page.locator('#ws-report-table').inner_text()
                assert 'DEMO' in page.locator('#ws-report-table').inner_text()
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'04-finpoint-reports.png'),full_page=True)
                page.locator('#navigation button[data-page=autopilot]').click()
                page.locator('#ap-panel').wait_for(state='visible')
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'05-finpoint-autopilot.png'),full_page=True)
                page.locator('#navigation button[data-page=alerts]').click()
                page.locator('#advisor-list').wait_for(state='visible')
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'06-finpoint-alerts.png'),full_page=True)
                page.locator('#navigation button[data-page=license]').click()
                page.locator('#license-device').wait_for(state='visible')
                page.locator('#desktop-local-ops').wait_for(state='visible',timeout=12000)
                expect(page.locator('#license-overview-grid, .license-overview-grid')).to_be_visible()
                assert 'chưa' in page.locator('#readiness-summary').inner_text().lower()
                # Technical checks and backup are hidden by default, not removed.
                expect(page.locator('#license-readiness-detail')).not_to_have_attribute('open','')
                page.locator('#license-readiness-detail > summary').click()
                assert 'CHƯA XÁC MINH' in page.locator('#readiness-checks').inner_text()
                page.locator('#license-backup-detail > summary').click()
                page.locator('#secure-backup-password').fill('test-encrypted-backup-password-123456')
                page.locator('#secure-backup-confirm').fill('test-encrypted-backup-password-123456')
                with page.expect_download(timeout=30000) as result:
                    page.locator('#secure-backup-export').click()
                backup_download=result.value
                assert backup_download.suggested_filename.endswith('.lhmbak')
                assert page.locator('#secure-backup-password').input_value()==''
                page.wait_for_timeout(650)
                page.locator('#license-readiness-detail > summary').click()
                page.locator('#license-backup-detail > summary').click()
                page.screenshot(path=str(ARTIFACTS/'07-finpoint-license.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                page.screenshot(path=str(ARTIFACTS/'26-compact-license-mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
                # Header search is hidden on small screens. Ctrl+K must land on
                # the visible in-page search, never a display:none field.
                page.keyboard.press('Control+k')
                expect(page.locator('#page-accounts')).to_be_visible()
                expect(page.locator('#account-list-search')).to_be_focused()
                expect(page.locator('#account-list-search')).to_be_visible()
                page.locator('#account-list-search').fill('Preview')
                expect(page.locator('#global-account-search')).to_have_value('Preview')
                expect(page.locator('#account-search-status')).to_have_text('Hiển thị 1/1 tài khoản')
                page.screenshot(path=str(ARTIFACTS/'15-mobile-accounts-search.png'),full_page=True)
                page.locator('#account-list-search').fill('')
                page.locator('#ui-command-open').click()
                expect(page.locator('#ui-command-overlay')).to_be_visible()
                page.locator('#ui-command-input').fill('bao cao')
                expect(page.locator('#ui-command-results [data-page=reports]')).to_be_visible()
                page.wait_for_timeout(380)  # Capture AFTER palette entrance animation finishes
                assert page.locator('.ui-command-dialog').evaluate('node => getComputedStyle(node).opacity') == '1'
                page.screenshot(path=str(ARTIFACTS/'14-command-palette-mobile.png'))
                page.locator('#ui-command-results [data-page=reports]').click()
                expect(page.locator('#page-reports')).to_be_visible()
                expect(page.locator('#ui-command-overlay')).to_be_hidden()
                page.locator('#menu').click()
                page.locator('#sidebar-backdrop.open').wait_for(state='visible')
                assert page.locator('#menu').get_attribute('aria-expanded') == 'true'
                page.keyboard.press('Escape')
                assert page.locator('#sidebar').get_attribute('class').find('open') == -1
                assert page.locator('#menu').get_attribute('aria-expanded') == 'false'
                page.locator('#menu').click()
                page.locator('#sidebar-backdrop.open').wait_for(state='visible')
                page.locator('#navigation button[data-page=reports]').click()
                page.locator('#sidebar-backdrop.open').wait_for(state='hidden')
                page.locator('#page-reports').wait_for(state='visible')
                page.wait_for_timeout(400)
                page.wait_for_timeout(650)
                page.screenshot(path=str(ARTIFACTS/'08-finpoint-mobile-reports.png'),full_page=True)
                dock=page.locator('.ui-mobile-dock')
                expect(dock).to_be_visible()
                expect(dock.locator('[data-ui-tab=reports]')).to_have_attribute('aria-current','page')
                dock.locator('[data-ui-tab=accounts]').click()
                expect(page.locator('#page-accounts')).to_be_visible()
                expect(dock.locator('[data-ui-tab=accounts]')).to_have_attribute('aria-current','page')
                dock.locator('#ui-dock-more').click()
                expect(page.locator('#sidebar-backdrop.open')).to_be_visible()
                expect(dock.locator('#ui-dock-more')).to_have_attribute('aria-expanded','true')
                page.keyboard.press('Escape')
                expect(dock.locator('#ui-dock-more')).to_have_attribute('aria-expanded','false')
                dock.locator('[data-ui-tab=reports]').click()
                page.locator('#page-reports').wait_for(state='visible')
                page.emulate_media(reduced_motion='reduce')
                assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
                page.locator('#menu').click()
                page.locator('#sidebar-backdrop.open').wait_for(state='visible')
                page.keyboard.press('Escape')
                page.locator('#sidebar-backdrop.open').wait_for(state='hidden')
                print('PASS: Ctrl+K, mobile drawer, Escape, reduced-motion and real KPI animation')
                print('PASS: separate campaigns, autopilot, alerts, license and reports pages; report data is sourced from Demo API')
                print('PASS: Google/Meta selected separately, Demo not mixed, native API/UI flow works')
                browser.close()
        finally:
            proc.terminate()
            try: proc.wait(timeout=8)
            except subprocess.TimeoutExpired: proc.kill()


if __name__=='__main__':
    main()
