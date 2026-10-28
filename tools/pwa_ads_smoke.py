"""End-to-end: the PWA runs Google Ads like the Windows app, on the real Worker.

Starts tests/helpers/worker-dev-server.mjs (Worker + SQLite). Google's OAuth page
and Google Ads API are answered by in-test fakes at the browser network layer.
Covers: browser sign-in return, account discovery (incl. MCC child), live
dashboard figures, campaign scan with playbook findings, guarded pause with
read-back and audit, hard lock after the plan is revoked, and that no request to
LHM ever carries the Google access token.
"""
from __future__ import annotations
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright
from tools.build_github_pages import build

ROOT=Path(__file__).resolve().parents[1]
TOKEN="ya29.fixture-access-token-NOT-FOR-LHM"
CAMPAIGNS=[{"campaign":{"id":"55500011","name":"Search Hà Nội","status":"ENABLED","biddingStrategyType":"MANUAL_CPC"},
            "metrics":{"costMicros":"2500000000","impressions":"20000","clicks":"400","conversions":0,"conversionsValue":0}},
           {"campaign":{"id":"55500012","name":"Brand","status":"ENABLED"},
            "metrics":{"costMicros":"900000000","impressions":"5000","clicks":"120","conversions":12.0,"conversionsValue":4500000.0}}]
DAILY=[{"segments":{"date":"2026-10-20"},"metrics":{"costMicros":"1250000000000","impressions":"8000","clicks":"200","conversions":3.0,"conversionsValue":900000.0}},
       {"segments":{"date":"2026-10-21"},"metrics":{"costMicros":"750000000000","impressions":"4000","clicks":"100","conversions":1.0,"conversionsValue":300000.0}}]


class FakeGoogle:
    def __init__(self):
        self.status="ENABLED"
        self.mutations=[]
        self.lhm_requests=[]

    def oauth(self,route):
        q=parse_qs(urlsplit(route.request.url).query)
        assert q["response_type"]==["token"] and q["scope"]==["https://www.googleapis.com/auth/adwords"]
        target=q["redirect_uri"][0]+"#access_token="+TOKEN+"&token_type=Bearer&expires_in=3599&state="+q["state"][0]
        route.fulfill(status=302,headers={"Location":target})

    def ads(self,route):
        req=route.request
        assert req.headers.get("authorization")=="Bearer "+TOKEN
        url=req.url
        body=json.loads(req.post_data) if req.post_data else {}
        def reply(data,status=200):
            route.fulfill(status=status,content_type="application/json",body=json.dumps(data),
                          headers={"Access-Control-Allow-Origin":"*"})
        if url.endswith("customers:listAccessibleCustomers"):
            return reply({"resourceNames":["customers/1112223333"]})
        if url.endswith("/campaigns:mutate"):
            self.mutations.append(body)
            if not body.get("validateOnly"):
                self.status="PAUSED"
            return reply({"results":[{"resourceName":body["operations"][0]["update"]["resourceName"]}]})
        query=body.get("query","")
        if "FROM customer_client" in query:
            return reply([{"results":[{"customerClient":{"id":"1112223333","descriptiveName":"MCC chính","currencyCode":"VND","manager":True}},
                                      {"customerClient":{"id":"4445556666","descriptiveName":"Shop Thời Trang","currencyCode":"VND"}}]}])
        if "FROM customer WHERE segments.date" in query:
            assert req.headers.get("login-customer-id")=="1112223333"
            return reply([{"results":DAILY}])
        if "campaign.status FROM campaign WHERE campaign.id" in query:
            return reply([{"results":[{"campaign":{"id":"55500011","status":self.status}}]}])
        if "FROM campaign WHERE campaign.status != REMOVED" in query:
            return reply([{"results":CAMPAIGNS}])
        raise AssertionError("unexpected Google Ads call: "+url+" "+query)


def main():
    out=ROOT/"artifacts"/"ui-preview"
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        site=build(Path(temp)/"site")
        proc=subprocess.Popen(["node",str(ROOT/"tests/helpers/worker-dev-server.mjs"),str(site)],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=ROOT)
        try:
            line=proc.stdout.readline().strip()
            if not line.startswith("LISTENING "):
                raise SystemExit("dev server failed: "+line+proc.stderr.read())
            origin="http://127.0.0.1:"+line.split()[1]
            fake=FakeGoogle()
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                context=browser.new_context(viewport={"width":1280,"height":900})
                page=context.new_page()
                errors=[]
                page.on("pageerror",lambda e:errors.append(str(e)))
                page.on("request",lambda r:fake.lhm_requests.append((r.url,r.post_data or "",dict(r.headers)))
                        if r.url.startswith(origin) else None)
                context.route("https://accounts.google.com/**",fake.oauth)
                context.route("https://googleads.googleapis.com/**",fake.ads)

                # A paying customer signs in.
                api=context.request
                r=api.post(origin+"/api/admin/grant",data=json.dumps({"email":"shop@gmail.com","confirm_email":"shop@gmail.com",
                    "plan_code":"personal-1m","reference":"CK-PWA-ADS"}),headers={"Content-Type":"application/json"})
                assert r.status==201,r.text()
                page.goto(origin+"/__test/signin?sub=google-ads-shop&email=shop@gmail.com")
                page.locator("body:not(.customer-locked)").wait_for(timeout=15000)

                # Connect Google Ads in the browser; the token comes back to /local/oauth/google.
                page.locator('.pwa-nav [data-go="accounts"]').click()
                page.locator('#lhm-connections [data-connect="google"]').click()
                page.wait_for_url(origin+"/local/",timeout=15000)
                page.locator("body:not(.customer-locked)").wait_for(timeout=15000)
                page.locator('#lhm-connections [data-discover="google"]').wait_for()
                assert TOKEN not in page.url
                page.locator('#lhm-connections [data-discover="google"]').click()
                child=page.locator("#lhm-candidates li",has_text="Shop Thời Trang")
                child.wait_for()
                assert "qua MCC 1112223333" in child.inner_text()
                child.get_by_role("button",name="Thêm vào kho").click()
                child.get_by_text("Đã lưu").wait_for()

                # Live dashboard: 2 days -> 2,000,000 VND spend, 300 clicks, 4 conversions.
                page.locator('.pwa-nav [data-go="dashboard"]').click()
                page.locator("#lhm-dash-load").click()
                row=page.locator("#lhm-dash-table tbody tr").first
                row.wait_for()
                cells=row.locator("td").all_inner_texts()
                assert cells[0]=="Shop Thời Trang" and cells[1].startswith("2.000.000") and cells[3]=="300",cells
                assert cells[6]=="4" and cells[7].startswith("500.000"),cells
                page.screenshot(path=str(out/"lhm-pwa-live-dashboard.png"),full_page=True)

                # Campaign scan with the same playbook as the PC.
                page.locator('.pwa-nav [data-go="assistant"]').click()
                page.get_by_role("button",name="Quét chiến dịch").click()
                page.locator("#lhm-findings li",has_text="Chi tiêu chưa ghi nhận chuyển đổi").wait_for()
                assert page.locator("#lhm-opt-campaigns tbody tr").count()==2
                page.screenshot(path=str(out/"lhm-pwa-optimizer.png"),full_page=True)

                # Guarded pause: confirm, validateOnly, live mutate, read-back, audit.
                page.locator("#lhm-opt-campaigns tr",has_text="Search Hà Nội").get_by_role("button",name="Tạm dừng…").click()
                page.locator("#lhm-pause-dialog").wait_for()
                page.check("#lhm-pause-confirm")
                page.locator('#lhm-pause-form button[value="ok"]').click()
                page.locator("#lhm-opt-status",has_text="đang PAUSED").wait_for()
                assert [m["validateOnly"] for m in fake.mutations]==[True,False]
                page.locator("#lhm-audit li",has_text="pause_campaign").wait_for()

                # Hard lock: revoking the plan locks the app and the vault.
                lic=api.get(origin+"/api/admin/overview").json()["licenses"][0]["id"]
                assert api.post(origin+"/api/admin/licenses/revoke",data=json.dumps({"license_id":lic}),
                                headers={"Content-Type":"application/json"}).status==200
                page.evaluate("window.LHMCustomer.reload()")
                page.locator("body.customer-locked").wait_for(timeout=15000)
                assert page.evaluate("window.LHMDeviceVault.isUnlocked()") is False
                assert "thu hồi" in page.locator("#customer-state-note").inner_text()

                # The Google token never travelled to LHM.
                leaks=[u for u,body,headers in fake.lhm_requests if TOKEN in u or TOKEN in body or TOKEN in json.dumps(headers)]
                assert not leaks,leaks
                assert not errors,errors
                browser.close()
        finally:
            proc.terminate()
    print("PASS: PWA live Google Ads on the real Worker: browser sign-in, MCC discovery, live dashboard,"
          " playbook scan, guarded pause with read-back and audit, hard lock on revoke, no token sent to LHM")


if __name__=="__main__":
    main()
