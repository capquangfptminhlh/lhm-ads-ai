"""End-to-end: PWA customer and Admin against the REAL Worker on SQLite.

Starts tests/helpers/worker-dev-server.mjs (Worker + all D1 migrations, test-only
Google stand-in and Access JWT), then drives two Chromium pages:
customer orders a plan -> admin activates it -> customer is unlocked ->
admin grants by Gmail, finds the customer, blocks them -> customer is locked.
"""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from tools.build_github_pages import build

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts"/"ui-preview"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        site=build(Path(temp)/"site")
        proc=subprocess.Popen(["node",str(ROOT/"tests/helpers/worker-dev-server.mjs"),str(site)],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=ROOT)
        try:
            line=proc.stdout.readline().strip()
            if not line.startswith("LISTENING "):
                raise SystemExit("dev server failed: "+line+proc.stderr.read())
            origin="http://127.0.0.1:"+line.split()[1]
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                errors=[]
                customer=browser.new_context(viewport={"width":390,"height":844}).new_page()
                admin=browser.new_context(viewport={"width":1366,"height":900}).new_page()
                for page in (customer,admin):
                    page.on("pageerror",lambda e:errors.append(str(e)))
                    page.route("https://img.vietqr.io/**",lambda r:r.fulfill(status=200,content_type="image/png",body=b""))

                # Customer signs in with Gmail and orders a plan.
                customer.goto(origin+"/__test/signin?sub=google-1&email=Khach.Test@gmail.com&name=Kh%C3%A1ch%20Test")
                customer.locator(".customer-plan").first.wait_for()
                customer.locator("#customer-plan-submit").click()
                customer.locator("#customer-payment").wait_for()
                code=customer.locator("#customer-pay-code").inner_text()
                assert code.startswith("LHM") and len(code)==8,code
                assert customer.locator("body.customer-locked").count()==1

                # Admin sees the order by its payment code and activates it.
                admin.goto(origin+"/admin/")
                admin.locator("#workspace").wait_for()
                row=admin.locator("#order-list tr",has_text=code)
                row.wait_for()
                assert "✓ đã đăng nhập" in row.inner_text()
                admin.screenshot(path=str(OUT/"lhm-admin-pending.png"),full_page=True)
                row.get_by_role("button",name="Duyệt & kích hoạt").click()
                admin.fill("#payment-reference","FT26298TEST")
                admin.locator("#payment-review-form button[type=submit]").click()
                admin.locator("#message",has_text="Đã kích hoạt").wait_for()
                assert admin.locator("#order-empty").is_visible()

                # Customer is unlocked without re-entering anything.
                customer.evaluate("window.LHMCustomer.reload()")
                customer.locator("body:not(.customer-locked)").wait_for(timeout=15000)
                assert customer.locator(".pwa-shell").is_visible()

                # Admin grants a plan to a Gmail that has never signed in (typed with dots).
                admin.locator('nav button[data-tab="grant"]').click()
                admin.fill('#grant-form input[name="email"]',"Pilot.User@gmail.com")
                admin.fill('#grant-form input[name="confirm_email"]',"pilotuser@gmail.com")
                admin.fill('#grant-form input[name="days"]',"12")
                admin.fill('#grant-form input[name="reference"]',"PILOT-KH001")
                admin.check('#grant-form input[name="pilot"]')
                admin.once("dialog",lambda d:d.accept())
                admin.locator("#grant-form button[type=submit]").click()
                admin.locator("#grant-result").wait_for()
                assert "chưa đăng nhập Gmail này" in admin.locator("#grant-result").inner_text()

                # Search finds it whatever dots are typed; the detail shows the plan.
                admin.locator('nav button[data-tab="customers"]').click()
                admin.fill("#customer-search","pilot.user@googlemail.com")
                admin.locator("#customer-search-form button").click()
                admin.locator("#customer-list tr",has_text="Pilot.User@gmail.com".lower()).wait_for()
                admin.locator("#customer-list tr").first.get_by_role("button",name="Xem").click()
                admin.locator("#customer-detail").wait_for()
                plan_text=admin.locator("#cd-plan").inner_text()
                assert "Cá nhân · 1 tháng" in plan_text and "hết hạn" in plan_text,plan_text
                admin.screenshot(path=str(OUT/"lhm-admin-customer.png"),full_page=True)

                # Block the paying customer: every session ends, the PWA locks hard.
                admin.fill("#customer-search","khachtest@gmail.com")
                admin.locator("#customer-search-form button").click()
                admin.locator("#customer-list tr",has_text="khach.test@gmail.com").wait_for()
                admin.locator("#customer-list tr").first.get_by_role("button",name="Xem").click()
                admin.locator("#cd-devices tr",has_text="Chrome").wait_for()
                admin.once("dialog",lambda d:d.accept("kiểm thử"))
                admin.get_by_role("button",name="Khoá tài khoản").click()
                admin.locator("#cd-status",has_text="Đang khoá").wait_for()
                customer.evaluate("window.LHMCustomer.reload()")
                customer.locator("#customer-google-signin").wait_for()
                assert customer.locator("body.customer-locked").count()==1
                assert not customer.locator(".pwa-shell").is_visible()

                # Pilot migration: paste the CSV from tools/migrate_pilot_to_gmail.py --out.
                admin.locator('nav button[data-tab="grant"]').click()
                admin.locator("#grant summary",has_text="chuyển khách pilot").click()
                admin.fill("#bulk-csv","gmail,days,reference,note\nbulk.user@gmail.com,9,PILOT-KH009,Pilot license lic-9\n")
                admin.once("dialog",lambda d:d.accept())
                admin.locator("#bulk-run").click()
                admin.locator("#bulk-result li",has_text="bulk.user@gmail.com · 9 ngày").wait_for()

                # Plans tab lists the seeded pilot prices.
                admin.locator('nav button[data-tab="plans"]').click()
                assert admin.locator("#plan-list tr").count()>=4
                admin.screenshot(path=str(OUT/"lhm-admin-plans.png"),full_page=True)
                assert not errors,errors
                browser.close()
        finally:
            proc.terminate()
    print("PASS: real Worker + SQLite: PWA order, Admin activation by payment code, unlock,"
          " grant by Gmail, Gmail-normalized search, block -> hard lock")


if __name__=="__main__":
    main()
