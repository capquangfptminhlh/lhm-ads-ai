"""Deploy LHM Ads Cloudflare Worker with an existing, verified D1 database.

Requires a Cloudflare-authorized Wrangler environment (Workers Builds or CLI).
Never creates a database or guesses account/DB IDs. Fails before deployment if
D1 is missing, so commercial endpoints cannot silently ship without storage.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
DB_NAME="lhm-ads-commerce"
UUID=re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


def find_database_id() -> str:
    provided=os.getenv("LHM_COMMERCE_D1_DATABASE_ID","").strip()
    if provided:
        if not UUID.fullmatch(provided):
            raise RuntimeError("LHM_COMMERCE_D1_DATABASE_ID is not a valid D1 UUID")
        return provided
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
    if len(matches)!=1 or not UUID.fullmatch(str(matches[0].get("uuid") or matches[0].get("id") or "")):
        raise RuntimeError("Database lhm-ads-commerce not found or ambiguous; create/select it in the correct Cloudflare account")
    return str(matches[0].get("uuid") or matches[0].get("id"))


def make_config(database_id: str) -> str:
    base=(ROOT/"wrangler.toml").read_text(encoding="utf-8")
    if "[[d1_databases]]" in base:
        raise RuntimeError("wrangler.toml already defines D1 bindings; reconcile manually before deployment")
    return base.rstrip()+(
        "\n\n[[d1_databases]]\n"
        'binding = "COMMERCE_DB"\n'
        f'database_name = "{DB_NAME}"\n'
        f'database_id = "{database_id}"\n'
        'migrations_dir = "migrations"\n'
    )


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dry-run",action="store_true",help="Check and print binding name without deploying")
    args=p.parse_args()
    try:
        database_id=find_database_id()
        cfg=make_config(database_id)
        print(f"Verified D1 {DB_NAME}: {database_id[:8]}…")
        if args.dry_run:
            print("Binding COMMERCE_DB ready; no migration or deployment performed.")
            return 0
        if not (ROOT/"_site/index.html").exists():
            subprocess.run([sys.executable,"tools/build_github_pages.py","--output","_site"],
                cwd=ROOT,check=True)
        generated=ROOT/"wrangler.commerce.generated.toml"
        try:
            generated.write_text(cfg,encoding="utf-8")
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
        return 1


if __name__=="__main__":
    raise SystemExit(main())
