"""Chromium check of the Windows Gmail gate (static/desktop-cloud-login.js).

The pywebview bridge and the local /api/cloud-license/* routes are faked with the
shapes ads_core/desktop_cloud_license.py returns. Covers: expired plan hard-lock
with renewal link, device limit with explicit takeover, offline banner.
"""
from __future__ import annotations
import http.server
import json
import socketserver
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

STATIC=Path(__file__).resolve().parents[1]/"static"
PAGE=b"<!doctype html><html><head><meta charset='utf-8'></head><body><main id='studio'>Studio</main>" \
     b"<section id='login'>legacy login</section><script src='/static/desktop-cloud-login.js'></script></body></html>"
BRIDGE="""window.__opened=[];window.pywebview={api:{
 get_local_license_proof:async()=>'p'.repeat(64),
 open_license_url:async(u)=>{window.__opened.push(u);return true;}}};"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_GET(self):
        if self.path.startswith("/static/"):
            body=(STATIC/self.path[len("/static/"):]).read_bytes()
            self.send_response(200);self.send_header("Content-Type","text/javascript");self.end_headers();self.wfile.write(body)
        else:
            self.send_response(200);self.send_header("Content-Type","text/html");self.end_headers();self.wfile.write(PAGE)


class Server(socketserver.ThreadingMixIn,http.server.HTTPServer):
    daemon_threads=True


def run(scenario:dict):
    server=Server(("127.0.0.1",0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    calls=[]
    def api(route):
        path=route.request.url.split(str(server.server_address[1]),1)[1]
        body=json.loads(route.request.post_data) if route.request.post_data else {}
        calls.append((path,body))
        if path.startswith("/api/cloud-license/"):
            # Only the native window may drive licensing endpoints.
            assert route.request.headers.get("x-lhm-native-proof")=="p"*64
        reply=scenario.get((path,body.get("mode")),scenario.get(path,{"ok":True}))
        status=reply.pop("_status",200) if isinstance(reply,dict) else 200
        route.fulfill(status=status,content_type="application/json",body=json.dumps(reply))
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport={"width":1280,"height":800})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.add_init_script(BRIDGE)
            page.route("**/api/**",api)
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/")
            yield page,calls
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close()


def main():
    expired={"/api/cloud-license/status":{"enabled":True,"paired":True,"active":False,"email":"owner@gmail.com","reason":"SUBSCRIPTION_EXPIRED"},
             ("/api/cloud-license/attach","attach"):{"active":False,"reason":"SUBSCRIPTION_EXPIRED"}}
    for page,calls in run(expired):
        page.locator("#lhm-cloud-gate").wait_for()
        page.locator("#lhm-cloud-renew").wait_for()
        assert "hết hạn" in page.locator("#lhm-cloud-status").inner_text()
        assert not page.locator("#lhm-cloud-takeover").is_visible()
        page.locator("#lhm-cloud-renew").click()
        page.wait_for_function("window.__opened.includes('https://ads.lhmcrm.com/local/')")

    seat_limit={"/api/cloud-license/status":{"enabled":True,"paired":True,"active":False,"email":"owner@gmail.com"},
                ("/api/cloud-license/attach","attach"):{"active":False,"reason":"SEAT_LIMIT",
                  "devices":[{"label":"Chrome Android","last_seen_at":"2026-10-25T08:00:00Z"}]},
                ("/api/cloud-license/attach","takeover"):{"active":True,"expires_at":"2099-01-01T00:00:00Z"},
                "/api/studio/me":{"email":"owner@gmail.com"}}
    for page,calls in run(seat_limit):
        page.locator("#lhm-cloud-takeover").wait_for()
        assert page.locator("#lhm-cloud-devices li").count()==1
        assert not page.locator("#lhm-cloud-attach").is_visible()
        page.locator("#lhm-cloud-takeover").click()
        page.locator("#lhm-cloud-gate").wait_for(state="hidden")
        assert ("/api/cloud-license/attach",{"mode":"takeover"}) in calls

    offline={"/api/cloud-license/status":{"enabled":True,"paired":True,"active":True,"reason":"OFFLINE",
                                          "offline_until":"2099-01-03T10:00:00Z"},
             "/api/studio/me":{"email":"owner@gmail.com"}}
    for page,calls in run(offline):
        page.locator("#lhm-cloud-offline").wait_for()
        assert "offline" in page.locator("#lhm-cloud-offline").inner_text()
        page.locator("#lhm-cloud-gate").wait_for(state="hidden")
    print("PASS: Windows Gmail gate: expired hard lock with renewal link, device-limit takeover, offline banner")


if __name__=="__main__":
    main()
