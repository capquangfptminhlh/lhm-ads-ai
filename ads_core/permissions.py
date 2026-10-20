"""Read-only Ads permission diagnostics. Scope != effective write authorization."""
import json
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import Depends, HTTPException

from .app import app, browser_admin, get_account
from .db import connection, audit
from .providers import account_token

def flag(status="unverified", reason="Chưa thể xác minh."):
    return {"status":status,"detail":reason}

WRITES=("campaign_write","bid_write","budget_write","strategy_write")

def initial(a):
    d={"account_id":a["id"],"platform":a["platform"],
       "checked_at":datetime.now(timezone.utc).isoformat(),
       "granted_scopes":[],
       "note":"Các lệnh kiểm tra chỉ đọc; chưa có thao tác thay đổi quảng cáo."}
    for k in ("token","account_read","report_read","scope_read","scope_manage",*WRITES):
        d[k]=flag()
    for k in WRITES:
        d[k]=flag("unverified","Không thử thay đổi quảng cáo thật để kiểm tra quyền.")
    return d

def deny_write(d,reason):
    for k in WRITES:d[k]=flag("denied",reason)

async def google_check(a,c):
    d=initial(a)
    try:
        credentials=json.loads(account_token(a))
        fields={"client_id":credentials.get("client_id"),
                "refresh_token":credentials.get("refresh_token"),
                "grant_type":"refresh_token"}
        if not fields["client_id"] or not fields["refresh_token"]:
            raise ValueError("Missing refresh credentials")
        if credentials.get("client_secret"):fields["client_secret"]=credentials["client_secret"]
        r=await c.post("https://oauth2.googleapis.com/token",data=fields)
        if r.status_code!=200 or not r.json().get("access_token"):
            d["token"]=flag("denied","Không đổi được refresh token; kết nối có thể hết hạn.")
            d["account_read"]=flag("denied","OAuth chưa xác thực.")
            d["report_read"]=flag("denied","OAuth chưa xác thực.")
            deny_write(d,"OAuth chưa xác thực.")
            return d
        token=r.json()["access_token"]
        d["token"]=flag("confirmed","Google đã cấp access token hợp lệ.")
        scope_text=r.json().get("scope","")
        if scope_text:
            granted="https://www.googleapis.com/auth/adwords" in scope_text.split()
            if granted:d["granted_scopes"]=["https://www.googleapis.com/auth/adwords"]
            d["scope_read"]=flag("confirmed" if granted else "denied","OAuth Google Ads scope "+("có hiệu lực." if granted else "chưa được cấp."))
            d["scope_manage"]=flag("confirmed" if granted else "denied","Scope cho phép yêu cầu Ads API; quyền ghi thực tế còn tùy vai trò tài khoản." if granted else "Thiếu OAuth Ads API scope.")
            if not granted:deny_write(d,"Thiếu OAuth Google Ads API scope.")
        else:
            d["scope_read"]=flag("unverified","Refresh response không trả OAuth scopes.")
            d["scope_manage"]=flag("unverified","Không xác định được OAuth scope quản lý.")
        customer=str(a["external_id"]).replace("-","")
        if not re.fullmatch(r"\d{8,20}",customer):raise ValueError("invalid customer id")
        version=os.getenv("GOOGLE_ADS_API_VERSION","v25")
        if not re.fullmatch(r"v\d+",version):raise ValueError("invalid api version")
        headers={"Authorization":"Bearer "+token}
        dev=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN","")
        if dev:headers["developer-token"]=dev
        manager=str(credentials.get("login_customer_id") or "").replace("-","")
        if manager:
            if not re.fullmatch(r"\d{8,20}",manager):raise ValueError("invalid manager id")
            headers["login-customer-id"]=manager
        endpoint=f"https://googleads.googleapis.com/{version}/customers/{customer}/googleAds:searchStream"
        r=await c.post(endpoint,headers=headers,json={"query":"SELECT customer.id, customer.descriptive_name, customer.status FROM customer LIMIT 1"})
        if r.status_code==200:
            d["account_read"]=flag("confirmed","Đã đọc tài khoản Google Ads qua GAQL.")
        else:
            state="denied" if r.status_code in (401,403) else "unverified"
            d["account_read"]=flag(state,"Google Ads chưa cho đọc tài khoản này.")
            if state=="denied":deny_write(d,"Tài khoản này từ chối truy cập.")
            return d
        q=("SELECT segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks "
           "FROM customer WHERE segments.date DURING YESTERDAY ORDER BY segments.date ASC")
        r=await c.post(endpoint,headers=headers,json={"query":q})
        d["report_read"]=flag("confirmed" if r.status_code==200 else "denied" if r.status_code in (401,403) else "unverified",
                              "Google Ads cho phép đọc báo cáo." if r.status_code==200 else "Chưa đọc được báo cáo của tài khoản này.")
        d["note"]="Google OAuth scope không đủ để khẳng định quyền sửa chiến dịch, giá thầu, ngân sách hoặc chiến lược."
        return d
    except (ValueError,KeyError,TypeError,httpx.HTTPError):
        d["token"]=flag("unverified","Không thể kiểm tra Google OAuth ở thời điểm này.")
        return d

async def meta_check(a,c):
    d=initial(a)
    aid=str(a["external_id"]).removeprefix("act_")
    if not re.fullmatch(r"\d{4,30}",aid):
        d["account_read"]=flag("denied","Meta Ad Account ID không hợp lệ.")
        return d
    try:
        version=os.getenv("META_GRAPH_VERSION","v24.0")
        if not re.fullmatch(r"v\d+\.\d+",version):raise ValueError("version")
        token=account_token(a)
        base="https://graph.facebook.com/"+version
        headers={"Authorization":"Bearer "+token}
        # A system-user token may not support /me/permissions; do not call that denial.
        p=await c.get(base+"/me/permissions",headers=headers)
        if p.status_code==200:
            grant={str(x.get("permission")) for x in p.json().get("data",[])
                   if isinstance(x,dict) and x.get("status")=="granted"}
            d["granted_scopes"]=sorted(grant.intersection({"ads_read","ads_management","business_management"}))
            for field,scope in (("scope_read","ads_read"),("scope_manage","ads_management")):
                ok=scope in grant
                d[field]=flag("confirmed" if ok else "denied",scope+(" đã cấp." if ok else " chưa được cấp."))
            if "ads_management" not in grant:deny_write(d,"Token chưa được cấp ads_management.")
        else:
            d["scope_read"]=flag("unverified","Không đọc được scope; có thể là system-user token.")
            d["scope_manage"]=flag("unverified","Không thể khẳng định thiếu quyền khi API scope không khả dụng.")
        account=await c.get(base+"/act_"+aid,headers=headers,params={"fields":"id,name,account_status,currency"})
        if account.status_code!=200:
            d["account_read"]=flag("denied" if account.status_code in (401,403) else "unverified","Meta từ chối hoặc chưa xác nhận quyền vào tài khoản.")
            if account.status_code in (401,403):deny_write(d,"Meta từ chối quyền truy cập tài khoản.")
            return d
        d["token"]=flag("confirmed","Token đã được Meta chấp nhận cho tài khoản.")
        d["account_read"]=flag("confirmed","Đọc thông tin tài khoản Meta thành công.")
        insights=await c.get(base+"/act_"+aid+"/insights",headers=headers,
                             params={"fields":"spend,impressions,clicks","date_preset":"yesterday","limit":1})
        d["report_read"]=flag("confirmed" if insights.status_code==200 else "denied" if insights.status_code in (401,403) else "unverified",
                               "Đọc Meta Insights thành công." if insights.status_code==200 else "Chưa đọc được Meta Insights.")
        d["note"]="ads_management là quyền OAuth, chưa chứng minh được quyền chỉnh sửa từng tài khoản/campaign. Không gửi lệnh ghi khi kiểm tra."
        return d
    except (ValueError,KeyError,TypeError,httpx.HTTPError):
        d["token"]=flag("unverified","Không xác minh được Meta token; kiểm tra kết nối API.")
        return d

@app.post("/api/permissions/probe/{account_id}")
async def probe_permissions(account_id:int,ident=Depends(browser_admin)):
    """Explicitly initiated admin-only, session/CSRF/tenant protected, read-only."""
    a=get_account(account_id,ident["org_id"])
    if a["platform"] not in ("google","meta"):raise HTTPException(422,"Chỉ hỗ trợ Google Ads và Meta Ads.")
    if not a.get("token_ciphertext"):raise HTTPException(422,"Token chưa được kết nối hoặc đã thu hồi.")
    async with httpx.AsyncClient(timeout=httpx.Timeout(24.0,connect=6.0),trust_env=False) as client:
        result=await (google_check(a,client) if a["platform"]=="google" else meta_check(a,client))
    with connection() as db:
        audit(db,ident,"ads.permissions.probe",f"account=#{account_id};platform={a['platform']};report={result['report_read']['status']}")
    return result
