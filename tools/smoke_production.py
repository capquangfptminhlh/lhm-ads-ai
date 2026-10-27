"""Read-only real-production smoke tests for https://ads.lhmcrm.com.

Strict mode is the commercial release gate; it intentionally fails until D1,
Cloudflare Access, migrations, and unauthenticated route protection are live.
No customer data, Ads credentials, keys, or login tokens are sent.
"""
from __future__ import annotations
import argparse
import json
from urllib import request, error

BASE="https://ads.lhmcrm.com"


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER=request.build_opener(NoRedirect)


def call(path, data=None, *, base=BASE):
    headers={"Accept":"application/json"} if path.startswith("/api/") else {}
    # Cloudflare's bot protection answers 403 to the default Python-urllib agent,
    # which would also hide whether Admin is really behind Access.
    headers["User-Agent"]="LHM-Ads-Smoke/1.0 (+https://github.com/capquangfptminhlh/lhm-ads-ai)"
    if data is not None:
        headers["Content-Type"]="application/json"
    req=request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
        headers=headers,method="POST" if data is not None else "GET")
    try:
        r=OPENER.open(req,timeout=20)
    except error.HTTPError as e:
        r=e
    body=r.read(500_000).decode("utf-8","replace")
    return r.status,body


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--strict",action="store_true",help="Fail unless commercial Admin is ready")
    a=ap.parse_args()
    bad=[]
    for path in ("/","/local/"):
        try:
            status,html=call(path)
            ok=status==200 and "LHM" in html
            print(f"{path}: HTTP {status} {'PASS' if ok else 'FAIL'}")
            if not ok:bad.append(path+" failed to load")
        except Exception as e:bad.append(path+": "+str(e))
    try:
        code,body=call("/api/_hosting/status")
        state=json.loads(body)
        print("/api/_hosting/status:",code)
        for k in ("commerce_binding_present","commerce_access_configured",
                  "commerce_schema_ready","commerce_admin_config_ready"):
            print(" ",k,"=",state.get(k))
            if a.strict and state.get(k) is not True:bad.append(k+" is not ready")
        if code!=200:bad.append("hosting status returned "+str(code))
    except Exception as e:bad.append("hosting status: "+str(e))
    try:
        code,_=call("/admin/")
        print("/admin/ unauthenticated:",code)
        if a.strict and code not in (301,302,303,307,308,401,403):
            bad.append("Admin HTML is publicly accessible; configure Cloudflare Access")
    except Exception as e:bad.append("admin path: "+str(e))
    try:
        code,_=call("/api/admin/overview")
        print("/api/admin/overview unauthenticated:",code)
        if a.strict and code not in (301,302,303,307,308,401,403):
            bad.append("Admin API not correctly protected (response "+str(code)+")")
    except Exception as e:bad.append("admin API: "+str(e))
    try:
        code,body=call("/api/license/verify",{"key":"invalid"})
        print("/api/license/verify malformed-key:",code)
        if a.strict and not (code==200 and json.loads(body).get("valid") is False):
            bad.append("license service not ready")
    except Exception as e:bad.append("license verifier: "+str(e))
    for reason in bad:print("FAIL:",reason)
    print("RESULT:","FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__=="__main__":
    raise SystemExit(main())
