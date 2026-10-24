"""End-to-end real Chromium test: browser IndexedDB ciphertext, no remote Ads transfer."""
from __future__ import annotations
import http.server
import json
import socketserver
import tempfile
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from tools.build_github_pages import build

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

def main():
    with tempfile.TemporaryDirectory() as folder:
        output=build(Path(folder)/'site')
        class Server(socketserver.ThreadingMixIn,http.server.HTTPServer):
            daemon_threads=True
            allow_reuse_address=True
        import os
        original=os.getcwd()
        os.chdir(output)
        server=Server(('127.0.0.1',0),QuietHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':390,'height':844})
                api_writes=[]
                def intercepted(route):
                    if route.request.method!='GET' or '/api/' in route.request.url:
                        api_writes.append((route.request.method,route.request.url))
                    route.continue_()
                page.route('**/*',intercepted)
                page.goto(f'http://127.0.0.1:{server.server_address[1]}/studio/',wait_until='domcontentloaded')
                page.locator('#device-only-vault').wait_for(timeout=10000)
                page.locator('#lhm-vault-access-action').get_attribute('type')
                assert page.locator('#lhm-static-api-guard').count()==1
                passphrase='A-vault-test-password-2026!'
                page.fill('#lhm-vault-password',passphrase)
                page.click('#lhm-vault-access-action')
                page.locator('#lhm-vault-unlocked:not(.hidden)').wait_for(timeout=15000)
                marker='LOCAL-ADS-SECRET-NOT-FOR-NETWORK-82016'
                page.evaluate("""async token => {
                    await window.LHMDeviceVault.upsertAccount({
                        platform:'google',accountId:'123-456-7890',
                        label:'Device only',
                        accessToken:token,refreshToken:'local-refresh-test-8888'
                    });
                }""",marker)
                saved=page.evaluate("""async () => {
                    let db=await new Promise((resolve,reject)=>{
                       const request=indexedDB.open('lhm-ads-device-only-v1');
                       request.onsuccess=()=>resolve(request.result);
                       request.onerror=()=>reject(request.error);
                    });
                    let row=await new Promise((resolve,reject)=>{
                        const tx=db.transaction('vaults','readonly');
                        const req=tx.objectStore('vaults').get('default');
                        req.onsuccess=()=>resolve(req.result);
                        req.onerror=()=>reject(req.error);
                    });
                    db.close();return JSON.stringify(row);
                }""")
                assert '123-456-7890' not in saved
                assert marker not in saved and 'local-refresh-test' not in saved
                assert 'Device only' not in saved
                assert '"ciphertext"' in saved and '"salt"' in saved
                entries=page.evaluate('window.LHMDeviceVault.listAccounts()')
                assert len(entries)==1 and entries[0]['accountId']=='123-456-7890'
                assert marker not in json.dumps(entries)
                assert page.locator('#lhm-local-import').count()==1
                csv='date,spend,clicks,impressions,currency\\n2026-10-23,210000,18,900,VND\\n2026-10-22,120000,10,400,VND'
                report=page.evaluate("csv => window.LHMOfflineCSV.parseCSV(csv)",csv)
                assert len(report)==2 and report[0]['spend']==210000
                invalid=page.evaluate("""() => {
                    try{window.LHMOfflineCSV.parseCSV('date,spend,clicks,impressions,currency\\n2026-02-30,20,1,2,VND');
                        return false;}catch(e){return true;}
                }""")
                assert invalid
                page.evaluate("""async rows => {
                    const id=window.LHMDeviceVault.listAccounts()[0].localId;
                    await window.LHMDeviceVault.importDailyReport(id,rows);
                    await window.LHMDeviceVault.setDailyBudget(id,200000,true);
                    window.dispatchEvent(new Event('lhm:vault-change'));
                }""",report)
                assert '210.000' in page.locator('#lhm-local-alert-list').inner_text()
                assert 'CSV thủ công' in page.locator('#lhm-local-alert-list').inner_text()
                assert len(page.evaluate('window.LHMDeviceVault.listDailyReports()'))==2
                assert len(page.evaluate('window.LHMDeviceVault.listLocalAlerts()'))==1
                saved_again=page.evaluate("""async () => {
                    const req=indexedDB.open('lhm-ads-device-only-v1');
                    const db=await new Promise((resolve,reject)=>{req.onsuccess=()=>resolve(req.result);req.onerror=reject;});
                    const tx=db.transaction('vaults','readonly');
                    const get=tx.objectStore('vaults').get('default');
                    const item=await new Promise((resolve,reject)=>{get.onsuccess=()=>resolve(get.result);get.onerror=reject;});
                    db.close();return JSON.stringify(item);
                }""")
                assert '210000' not in saved_again and '200000' not in saved_again
                encrypted=page.evaluate("window.LHMDeviceVault.encryptedBackup()")
                assert marker not in encrypted
                page.evaluate("window.LHMDeviceVault.lock()")
                wrong=page.evaluate("""async () => {
                    try {await window.LHMDeviceVault.unlock('wrong-vault-password');return false;}
                    catch(e){return true;}
                }""")
                assert wrong
                assert page.evaluate('window.LHMDeviceVault.isUnlocked()') is False
                page.reload(wait_until='domcontentloaded')
                page.locator('#device-only-vault').wait_for(timeout=10000)
                page.fill('#lhm-vault-password',passphrase)
                page.click('#lhm-vault-access-action')
                page.locator('#lhm-vault-unlocked:not(.hidden)').wait_for(timeout=15000)
                assert len(page.evaluate('window.LHMDeviceVault.listAccounts()'))==1
                assert len(page.evaluate('window.LHMDeviceVault.listDailyReports()'))==2
                assert len(page.evaluate('window.LHMDeviceVault.listLocalAlerts()'))==1
                page.evaluate('window.LHMDeviceVault.destroy()')
                assert page.evaluate('window.LHMDeviceVault.exists()') is False
                assert not any('/api/' in u and method!='GET' for method,u in api_writes)
                browser.close()
                print('PASS: real Chromium 390px PWA encrypted vault, CSV parsing/reporting, local budget alerts, lock/reload/delete and no Ads API writes')
        finally:
            server.shutdown()
            server.server_close()
            os.chdir(original)

if __name__=='__main__':main()
