"""Real Chromium walk through the Gmail plan gate of the hosted PWA.

The /api/auth/* routes are answered by an in-test fake that follows the Worker's
contract (workers/ads-api/src/google-subscription.js), so no Google, Cloudflare
or bank is contacted. Covers: plan picker, order + VietQR panel, activation,
device limit with explicit takeover, expiring banner and the hard lock.
"""
from __future__ import annotations
import base64
import http.server
import json
import os
import socketserver
import tempfile
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from tools.build_github_pages import build

PNG=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
PLANS=[{"code":"personal-1m","name":"Cá nhân · 1 tháng","seat_limit":2,"months":1,"price_vnd":499000,"available":True},
       {"code":"personal-6m","name":"Cá nhân · 6 tháng","seat_limit":2,"months":6,"price_vnd":2545000,"available":True}]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*_args):pass


class Server(socketserver.ThreadingMixIn,http.server.HTTPServer):
    daemon_threads=True
    allow_reuse_address=True


class FakeWorker:
    def __init__(self):
        self.state="none"
        self.order=None
        self.seat_full_once=True
        self.calls=[]

    def session(self):
        plan=None
        if self.state=="active":
            plan={"code":"personal-1m","name":"Cá nhân · 1 tháng","seat_limit":2,
                  "expires_at":"2099-01-03T00:00:00.000Z","days_left":2,"expiring_soon":True}
        return {"authenticated":True,"account_id":"11111111-1111-4111-8111-111111111111","email":"khach@gmail.com",
                "name":"Khách","picture":None,"state":self.state,"subscribed":self.state=="active","plan":plan,
                "pending_order":self.order if self.state=="pending" else None,"seats":None,
                "expired_at":"2026-10-01T00:00:00.000Z" if self.state=="expired" else None,"heartbeat_seconds":300}

    def handle(self,route):
        req=route.request
        path=req.url.split("://",1)[1].split("/",1)[1].split("?")[0]
        path="/"+path
        body=json.loads(req.post_data) if req.post_data else {}
        self.calls.append((req.method,path,body))
        def reply(data,status=200):
            route.fulfill(status=status,content_type="application/json",body=json.dumps(data))
        if path=="/api/auth/session":return reply(self.session())
        if path=="/api/auth/plans":return reply({"plans":PLANS})
        if path=="/api/auth/plan":
            plan=next(p for p in PLANS if p["code"]==body["plan_code"])
            self.order={"id":"22222222-2222-4222-8222-222222222222","payment_code":"LHM7K3Q9","amount_vnd":plan["price_vnd"],
                        "plan_code":plan["code"],"plan_name":plan["name"],"expires_at":"2099-01-01T00:00:00.000Z",
                        "payment":{"configured":True,"account_no":"0123456789","account_name":"NGUYEN VAN A",
                                   "amount_vnd":plan["price_vnd"],"transfer_content":"LHM7K3Q9",
                                   "qr_url":"https://img.vietqr.io/image/970436-0123456789-compact2.png?amount=1&addInfo=LHM7K3Q9"}}
            self.state="pending"
            return reply({**self.order,"status":"pending"},201)
        if path=="/api/auth/seat":
            if self.state!="active":
                return reply({"error":"Gói đã hết hạn.","code":"SUBSCRIPTION_EXPIRED"},402)
            if self.seat_full_once and body.get("mode")=="attach":
                self.seat_full_once=False
                return reply({"error":"Đã dùng hết số máy của gói.","code":"SEAT_LIMIT","seat_limit":2,"devices":[
                    {"id":"a"*12,"label":"Chrome Android","last_seen_at":"2026-10-25T08:00:00.000Z"},
                    {"id":"b"*12,"label":"Máy tính Windows","last_seen_at":"2026-10-25T09:00:00.000Z"}]},409)
            return reply({"active":True,"seat_limit":2,"occupied":2,"heartbeat_seconds":300,"expires_at":"2099-01-03T00:00:00.000Z"})
        if path=="/api/auth/devices":return reply({"seat_limit":2,"devices":[]})
        return reply({"ok":True})


def main():
    out=Path(__file__).resolve().parents[1]/"artifacts"/"ui-preview"
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        site=build(Path(temp)/"site")
        old=os.getcwd();os.chdir(site)
        server=Server(("127.0.0.1",0),Quiet)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        fake=FakeWorker()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page(viewport={"width":390,"height":844})
                errors=[]
                page.on("pageerror",lambda e:errors.append(str(e)))
                page.route("**/api/auth/**",fake.handle)
                page.route("https://img.vietqr.io/**",lambda r:r.fulfill(status=200,content_type="image/png",body=PNG))
                page.goto(f"http://127.0.0.1:{server.server_address[1]}/local/",wait_until="domcontentloaded")

                # No plan: plan picker, app and vault stay locked.
                page.locator("#customer-purchase").wait_for()
                page.locator(".customer-plan").first.wait_for()
                assert page.locator(".customer-plan").count()==2
                assert not page.locator("#customer-google-signin").is_visible()
                page.wait_for_timeout(800)
                assert page.locator("#customer-email").inner_text()=="khach@gmail.com"
                assert page.locator("body.customer-locked").count()==1
                assert not page.locator(".pwa-shell").is_visible()
                page.screenshot(path=str(out/"lhm-pwa-plans-mobile.png"),full_page=True)

                # Order -> bank transfer panel with VietQR and payment code.
                page.locator("#customer-plan-submit").click()
                page.locator("#customer-payment").wait_for()
                assert page.locator("#customer-pay-code").inner_text()=="LHM7K3Q9"
                assert page.locator("#customer-pay-amount").inner_text().startswith("499")
                assert page.locator("#customer-qr").is_visible()
                assert ("POST","/api/auth/plan",{"plan_code":"personal-1m"}) in fake.calls
                page.screenshot(path=str(out/"lhm-pwa-payment-mobile.png"),full_page=True)

                # Admin activates; the device limit asks before taking a seat.
                fake.state="active"
                page.evaluate("window.LHMCustomer.reload()")
                page.locator("#customer-seat-limit").wait_for()
                assert page.locator("#customer-seat-list li").count()==2
                assert page.locator("body.customer-locked").count()==1
                page.locator("#customer-takeover").click()
                page.locator("body:not(.customer-locked)").wait_for(timeout=10000)
                assert ("POST","/api/auth/seat") in [(m,p) for m,p,_ in fake.calls if _.get("mode")=="takeover"]
                page.locator("#lhm-plan-banner").wait_for()
                assert "2 ngày" in page.locator("#lhm-plan-banner-text").inner_text()
                page.screenshot(path=str(out/"lhm-pwa-active-banner-mobile.png"),full_page=True)

                # Expired: hard lock, renewal offered, data kept.
                fake.state="expired"
                page.evaluate("window.LHMCustomer.reload()")
                page.locator("#customer-purchase").wait_for()
                assert page.locator("body.customer-locked").count()==1
                assert "hết hạn" in page.locator("#customer-state-note").inner_text()
                assert not page.locator(".pwa-shell").is_visible()
                assert page.evaluate("window.LHMDeviceVault ? window.LHMDeviceVault.isUnlocked() : false") is False
                page.screenshot(path=str(out/"lhm-pwa-expired-mobile.png"),full_page=True)
                assert not errors,errors
                browser.close()
        finally:
            server.shutdown();server.server_close();os.chdir(old)
    print("PASS: PWA Gmail plan gate: plan picker, VietQR payment, activation, device-limit takeover,"
          " expiring banner and hard lock on expiry")


if __name__=="__main__":
    main()
