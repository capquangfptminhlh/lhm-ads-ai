"""Deploy LHM Ads Cloudflare Worker with an existing, verified D1 database.

Requires a Cloudflare-authorized Wrangler environment (Workers Builds or CLI).
Fails before deployment if D1 is missing, unless explicitly opted into --create-db.
Never guesses account IDs or D1 names; defaults to read-only discovery.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
DB_NAME="lhm-ads-commerce"
UUID=re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


def find_database_id(create_missing: bool = False) -> str:
    provided=os.getenv("LHM_COMMERCE_D1_DATABASE_ID","").strip()
    if provided and not UUID.fullmatch(provided):
        raise RuntimeError("LHM_COMMERCE_D1_DATABASE_ID is not a valid D1 UUID")
    # Always verify even user-supplied UUID against the correct account's D1 list.
    p=subprocess.run(["npx","wrangler","d1","list","--json"],
        cwd=ROOT,capture_output=True,text=True,check=True)
    try:
        payload=json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError("Cannot parse Wrangler D1 list; check Cloudflare authentication") from e
    if isinstance(payload,dict):
        payload=payload.get("result",payload.get("databases",[]))
    if not isinstance(payload,list):
        raise RuntimeError("Unexpected Wrangler D1 listing format")
    matches=[d for d in payload if isinstance(d,dict) and d.get("name")==DB_NAME]
    if len(matches)>1:
        raise RuntimeError("Multiple D1 databases with the same name; refusing to guess")
    if len(matches)==1:
        db_id=str(matches[0].get("uuid") or matches[0].get("id") or "")
        if not UUID.fullmatch(db_id):
            raise RuntimeError("Invalid database UUID returned by Cloudflare")
        if provided and provided.lower()!=db_id.lower():
            raise RuntimeError("Provided D1 UUID does not match the account's named database")
        return db_id
    if not create_missing:
        raise RuntimeError("D1 lhm-ads-commerce missing. Enable explicit --create-db to provision in the selected account.")
    return create_database()


def create_database() -> str:
    """Create the one explicitly named database only with verified account-scoped credentials."""
    account=os.getenv("CLOUDFLARE_ACCOUNT_ID","").strip()
    token=os.getenv("CLOUDFLARE_API_TOKEN","").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}",account) or not token:
        raise RuntimeError("Valid CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required for --create-db")
    url=f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database"
    req=urllib.request.Request(url,
        data=json.dumps({"name":DB_NAME}).encode("utf-8"),
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            payload=json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError("D1 creation failed (HTTP "+str(error.code)+"). Check scoped D1 Write permission.") from None
    if not payload.get("success"):
        raise RuntimeError("Cloudflare rejected D1 creation")
    result=payload.get("result") or {}
    db_id=str(result.get("uuid") or "")
    if result.get("name")!=DB_NAME or not UUID.fullmatch(db_id):
        raise RuntimeError("D1 creation returned unexpected name or UUID; aborting deployment")
    return db_id


def make_config(database_id: str) -> str:
    base=(ROOT/"wrangler.toml").read_text(encoding="utf-8")
    parsed=tomllib.loads(base)
    configured=parsed.get("d1_databases") or []
    if configured:
        if not isinstance(configured,list) or len(configured)!=1:
            raise RuntimeError("Unexpected D1 bindings in wrangler.toml; inspect manually")
        item=configured[0]
        if item.get("binding")!="COMMERCE_DB" or item.get("database_name")!=DB_NAME or item.get("database_id")!=database_id:
            raise RuntimeError("D1 binding does not match the verified Cloudflare account/database")
        if item.get("migrations_dir")!="migrations":
            raise RuntimeError("D1 migrations directory is inconsistent")
        return base
    return base.rstrip()+(
        "\n\n[[d1_databases]]\n"
        'binding = "COMMERCE_DB"\n'
        f'database_name = "{DB_NAME}"\n'
        f'database_id = "{database_id}"\n'
        'migrations_dir = "migrations"\n'
    )



def confirm_pre_migration_restore_point(config_file: Path) -> str:
    """Require D1 Time Travel rollback evidence before modifying production.

    Bookmarks are metadata; do not export live customer data into CI artifacts.
    """
    result = subprocess.run(
        ["npx", "wrangler", "d1", "time-travel", "info", DB_NAME,
         "--config", str(config_file)],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    # Wrangler prints a suggested restore command containing the exact bookmark.
    match = re.search(r"--bookmark=([0-9a-f]{8}(?:-[0-9a-f]{8}){2}-[0-9a-f]{32})\b",
                      result.stdout, flags=re.IGNORECASE)
    if not match:
        raise RuntimeError("No D1 Time Travel restore bookmark; refusing production migrations")
    bookmark = match.group(1)
    print("Pre-migration D1 Time Travel restore point verified:", bookmark)
    return bookmark


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dry-run",action="store_true",help="Check and print binding name without deploying")
    p.add_argument("--create-db",action="store_true",help="Explicit opt-in: create missing commerce D1 in selected Cloudflare account")
    p.add_argument("--provision-only",action="store_true",help="Discover or create D1, without migrating or deploying")
    args=p.parse_args()
    if args.dry_run and args.create_db:
        p.error("--dry-run never creates a database; use --provision-only --create-db")
    try:
        database_id=find_database_id(create_missing=args.create_db)
        cfg=make_config(database_id)
        print(f"Verified D1 {DB_NAME}: {database_id[:8]}…")
        if args.provision_only:
            print("D1 provisioned or found. No migrations or deployment performed.")
            return 0
        if args.dry_run:
            print("Binding COMMERCE_DB ready; no migration or deployment performed.")
            return 0
        if not (ROOT/"_site/index.html").exists():
            subprocess.run([sys.executable,"tools/build_github_pages.py","--output","_site"],
                cwd=ROOT,check=True)
        generated=ROOT/"wrangler.commerce.generated.toml"
        try:
            generated.write_text(cfg,encoding="utf-8")
            confirm_pre_migration_restore_point(generated)
            subprocess.run(["npx","wrangler","d1","migrations","apply",DB_NAME,
                "--remote","--config",str(generated)],cwd=ROOT,check=True)
            subprocess.run(["npx","wrangler","deploy","--config",str(generated)],
                cwd=ROOT,check=True)
        finally:
            generated.unlink(missing_ok=True)
        print("Worker deployed with D1. Cloudflare Access variables/policies MUST still be tested.")
        return 0
    except (RuntimeError,subprocess.CalledProcessError) as e:
        print("DEPLOY BLOCKED:",str(e),file=sys.stderr)
        # Wrangler explains permission/account errors on its own output; captured
        # output would otherwise be lost. It never echoes the API token.
        for stream in (getattr(e,"stdout",None),getattr(e,"stderr",None)):
            if stream:
                print(stream[-4000:],file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
