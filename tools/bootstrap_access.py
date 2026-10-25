"""Provision/check only LHM Ads AI's Cloudflare Access application, opt-in.

Requires explicitly scoped CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID,
LHM_ADMIN_EMAIL. No credentials or user email are logged. Does not change
unrelated Access applications or create a Zero Trust organization.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from deploy_commerce import find_database_id, make_config
import urllib.request
import urllib.error

ACCOUNT_RE=re.compile(r"^[a-fA-F0-9]{32}$")
EMAIL_RE=re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DOMAIN_RE=re.compile(r"^[a-z0-9-]+\.cloudflareaccess\.com$")
TARGETS={
    "ads.lhmcrm.com/admin",
    "ads.lhmcrm.com/admin/*",
    "ads.lhmcrm.com/api/admin/*",
}
NAME="LHM Ads AI Admin"
BASE="https://api.cloudflare.com/client/v4"


class BootstrapError(RuntimeError):
    pass


def api(method: str, path: str, body: dict | None = None):
    token=os.getenv("CLOUDFLARE_API_TOKEN","").strip()
    account=os.getenv("CLOUDFLARE_ACCOUNT_ID","").strip()
    if not token or not ACCOUNT_RE.fullmatch(account):
        raise BootstrapError("Cloudflare token/account ID missing or invalid")
    url=BASE+f"/accounts/{account}"+path
    headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"}
    data=json.dumps(body).encode("utf-8") if body is not None else None
    req=urllib.request.Request(url,method=method,headers=headers,data=data)
    try:
        with urllib.request.urlopen(req,timeout=30) as resp:
            payload=json.load(resp)
    except urllib.error.HTTPError as err:
        # Cloudflare's error codes say whether the token lacks a permission or
        # Zero Trust is not set up; they never contain the token itself.
        try:
            details="; ".join(f"{e.get('code')}: {e.get('message')}"
                              for e in json.load(err).get("errors") or [])
        except Exception:
            details=""
        raise BootstrapError(f"Cloudflare API {method} {path.split('?')[0]} failed with HTTP {err.code}"
                             f"{' ('+details+')' if details else ''}; check Access permissions") from None
    except urllib.error.URLError:
        raise BootstrapError("Cloudflare API unavailable") from None
    if not payload.get("success"):
        raise BootstrapError("Cloudflare API rejected Access request")
    return payload.get("result")


def app_destinations(app):
    dest=set()
    for item in app.get("destinations") or []:
        if isinstance(item,dict) and item.get("type","public")=="public" and item.get("uri"):
            dest.add(item["uri"].replace("https://","").rstrip("/"))
    # Only recognize the exact configured destination set, not broad wildcards.
    return dest


def overlaps_admin(app):
    """Fail closed if another Access app could already protect either Admin path."""
    from fnmatch import fnmatchcase
    probes=(
        "ads.lhmcrm.com/admin",
        "ads.lhmcrm.com/admin/",
        "ads.lhmcrm.com/admin/index.html",
        "ads.lhmcrm.com/api/admin/overview",
    )
    candidate=set(app_destinations(app))
    raw=app.get("domain")
    if isinstance(raw,str):
        candidate.add(raw.replace("https://","").rstrip("/"))
    for pattern in candidate:
        if fnmatchcase(pattern,"*.lhmcrm.com"):
            return True
        if any(fnmatchcase(p,pattern) for p in probes):
            return True
        if pattern in ("ads.lhmcrm.com","ads.lhmcrm.com/*"):
            return True
        if pattern.startswith("ads.lhmcrm.com/"):
            path=pattern[len("ads.lhmcrm.com/"):]
            if path.startswith(("admin","api/admin")):
                return True
    return False


def verify_owner_policy(app_id: str, email: str):
    """Query actual Access policy, not merely the app name or destinations."""
    if not re.fullmatch(r"[a-zA-Z0-9-]{20,64}",app_id):
        raise BootstrapError("Access application ID is missing or invalid")
    policies=api("GET",f"/access/apps/{app_id}/policies?per_page=100")
    if not isinstance(policies,list) or len(policies)!=1:
        raise BootstrapError("Expected exactly one owner-only Access policy")
    policy=policies[0]
    policy_id=policy.get("id") if isinstance(policy,dict) else None
    if not isinstance(policy_id,str) or not re.fullmatch(r"[a-zA-Z0-9-]{20,64}",policy_id):
        raise BootstrapError("Access policy ID is missing or invalid")
    full=api("GET",f"/access/apps/{app_id}/policies/{policy_id}")
    if not isinstance(full,dict) or full.get("decision")!="allow":
        raise BootstrapError("Access policy does not grant owner-only Allow")
    expected=[{"email":{"email":email}}]
    if full.get("include")!=expected or full.get("exclude") or full.get("require"):
        raise BootstrapError("Access policy is not restricted to the configured owner email")
    return True


def find_application(apps):
    relevant=[]
    for app in apps:
        if not isinstance(app,dict):
            continue
        paths=app_destinations(app)
        if app.get("name")==NAME or paths & TARGETS or overlaps_admin(app):
            relevant.append(app)
    if len(relevant)>1:
        raise BootstrapError("Multiple possibly matching Access apps; refusing to modify them")
    if relevant:
        app=relevant[0]
        if app.get("name")!=NAME or app_destinations(app)!=TARGETS:
            raise BootstrapError("Conflicting Access app/destinations; inspect Cloudflare Zero Trust manually")
        return app
    return None


def check_organization():
    organization=api("GET","/access/organizations")
    if not isinstance(organization,dict):
        raise BootstrapError("Zero Trust organization is not configured")
    domain=str(organization.get("auth_domain") or "").lower()
    domain=domain.replace("https://","").strip("/")
    if not DOMAIN_RE.fullmatch(domain):
        raise BootstrapError("Access auth_domain missing or unexpected")
    return domain


def bootstrap(create=False):
    email=os.getenv("LHM_ADMIN_EMAIL","").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise BootstrapError("LHM_ADMIN_EMAIL must be the intended owner's email (configured as a GitHub Secret)")
    team_domain=check_organization()
    apps=api("GET","/access/apps?per_page=100")
    if not isinstance(apps,list):
        raise BootstrapError("Unexpected Access apps response; refusing to create duplicates")
    if len(apps)>=100:
        raise BootstrapError("Access app list may be paginated; refusing to create duplicate apps")
    app=find_application(apps)
    if app is None and not create:
        raise BootstrapError("Access app missing. Explicit --create-app is required to provision it.")
    if app is None:
        payload={
            "name":NAME,
            "type":"self_hosted",
            "domain":"ads.lhmcrm.com/admin",
            "destinations":[{"type":"public","uri":uri} for uri in sorted(TARGETS)],
            "session_duration":"8h",
            "app_launcher_visible":False,
            "policies":[{
                "name":"LHM Ads AI owner only",
                "decision":"allow",
                "include":[{"email":{"email":email}}]
            }]
        }
        app=api("POST","/access/apps",payload)
    if not isinstance(app,dict) or app_destinations(app)!=TARGETS:
        raise BootstrapError("Access app response did not confirm all three protected routes")
    verify_owner_policy(str(app.get("id") or ""),email)
    aud=str(app.get("aud") or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{20,128}",aud):
        raise BootstrapError("Access audience is absent; review the app before deploying")
    return {"team_domain":team_domain,"aud":aud,"email":email}


def put_secret(name: str, value: str, config: Path):
    proc=subprocess.run(["npx","wrangler","secret","put",name,"--config",str(config)],
                        input=value+"\n",cwd=config.parent,
                        capture_output=True,text=True)
    if proc.returncode:
        # Do not print Wrangler subprocess stderr, which may contain sensitive data.
        raise BootstrapError(f"Unable to write Worker secret {name}; check Workers Scripts Write permission")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--create-app",action="store_true",
                        help="Explicitly create the named Access app if missing")
    parser.add_argument("--apply-worker-secrets",action="store_true",
                        help="Store Access issuer/audience/admin email as Worker secrets")
    args=parser.parse_args()
    try:
        result=bootstrap(create=args.create_app)
        if args.apply_worker_secrets:
            # Wrangler's secret updates must include the verified D1 binding.
            repo=Path(__file__).resolve().parents[1]
            db_id=find_database_id()
            config=repo/"wrangler.commerce.generated.toml"
            try:
                config.write_text(make_config(db_id),encoding="utf-8")
                for name,key in (("CF_ACCESS_TEAM_DOMAIN","team_domain"),
                                 ("CF_ACCESS_AUD","aud"),("ADMIN_EMAIL","email")):
                    put_secret(name,result[key],config)
            finally:
                config.unlink(missing_ok=True)
        print("Verified LHM Access app (3 protected paths, one audience).")
        print("Worker Access variables:", "written" if args.apply_worker_secrets else "not changed")
        print("Cloudflare Identity Provider and MFA must still be checked in dashboard.")
        return 0
    except BootstrapError as exc:
        print("ACCESS BOOTSTRAP BLOCKED:",exc,file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
