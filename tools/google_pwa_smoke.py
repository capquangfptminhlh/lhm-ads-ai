"""Real Chromium: Google login is the only required login; PWA Ads tokens stay local.
No Google Cloud credentials or Cloudflare server required for this isolated UI smoke.
"""
from __future__ import annotations
import functools
import http.server
import json
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright
from tools.build_github_pages import build

A = "e02ab0e4-c2b0-4a23-99a1-acd430b37fea"
B = "6e768f7e-30cc-4f45-a55a-f481a04a29a4"
SECRET = "LOCAL-ADS-TOKEN-MUST-NOT-LEAVE-THIS-BROWSER-2026"

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

def main():
    with tempfile.TemporaryDirectory() as tmp:
        output = build(Path(tmp)/"site")
        server=http.server.ThreadingHTTPServer(
            ("127.0.0.1",0),functools.partial(QuietHandler,directory=str(output)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        origin="http://127.0.0.1:"+str(server.server_address[1])
        current=[A]
        writes=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                context=browser.new_context(viewport={"width":390,"height":844})
                page=context.new_page()
                errors=[]
                page.on("pageerror",lambda ex: errors.append(str(ex)))
                def mock_auth(route):
                    path=route.request.url.split("/api/",1)[-1]
                    if path=="auth/session":
                        route.fulfill(status=200,content_type="application/json",body=json.dumps({
                            "authenticated":True,"account_id":current[0],
                            "email":("a" if current[0]==A else "b")+"@gmail.com",
                            "state":"active","subscribed":True,"heartbeat_seconds":300,
                            "plan":{"seat_limit":3,"expires_at":"2030-01-01T00:00:00Z","days_left":1000,"expiring_soon":False}
                        }))
                    elif path=="auth/seat":
                        route.fulfill(status=200,content_type="application/json",body=json.dumps({
                            "active":True,"seat_limit":3,"occupied":1,"ttl_seconds":120,
                            "account_id":current[0],"account_email":"account@gmail.com",
                            "expires_at":"2030-01-01T00:00:00Z"
                        }))
                    elif path=="auth/logout":
                        route.fulfill(status=200,content_type="application/json",body='{"ok":true}')
                    else:
                        route.fulfill(status=404,body="{}")
                page.route("**/api/auth/**",mock_auth)
                page.on("request",lambda req: writes.append(req.post_data or "")
                        if req.url.startswith(origin+"/api/") else None)
                page.goto(origin+"/local/",wait_until="domcontentloaded")
                page.wait_for_function("window.LHMDeviceVault?.isUnlocked() === true",timeout=20000)
                assert page.locator("#customer-google-signin").is_hidden()
                assert page.locator("#lhm-vault-password").is_hidden()
                assert page.locator(".pwa-sidebar").is_visible()
                page.evaluate("""async token => {
                    await window.LHMDeviceVault.upsertAccount({
                        platform:'google',accountId:'123-456-7890',
                        label:'Owner A', accessToken:token
                    });
                }""",SECRET)
                assert page.evaluate("window.LHMDeviceVault.listAccounts().length")==1
                stored=page.evaluate("""async () => {
                    const db=await new Promise((ok,no)=>{
                      const req=indexedDB.open('lhm-ads-device-only-v1');
                      req.onsuccess=()=>ok(req.result);req.onerror=()=>no(req.error);
                    });
                    try{
                      const row=await new Promise((ok,no)=>{
                        const req=db.transaction('vaults','readonly')
                          .objectStore('vaults').get('google:'+arguments[0]);
                        req.onsuccess=()=>ok(req.result);req.onerror=()=>no(req.error);
                      });
                      return JSON.stringify(row);
                    }finally{db.close();}
                }""".replace("arguments[0]","'"+A+"'"))
                assert SECRET not in stored and "123-456-7890" not in stored
                assert '"kdf":"DEVICE-KEY-AES256"' in stored
                # Account switch on same device MUST NOT decrypt A's Ads account.
                current[0]=B
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function("window.LHMDeviceVault?.isUnlocked() === true",timeout=20000)
                assert page.evaluate("window.LHMDeviceVault.listAccounts().length")==0
                current[0]=A
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function("window.LHMDeviceVault?.isUnlocked() === true",timeout=20000)
                assert page.evaluate("window.LHMDeviceVault.listAccounts().length")==1
                assert not any(SECRET in body for body in writes)
                assert not errors,errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print("PASS: Google-only PWA auto unlock, encrypted local Ads custody, tenant separation")

if __name__=="__main__":
    main()
