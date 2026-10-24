"""Persist only the verified D1 UUID in wrangler.toml for repeatable deploys.

D1 database identifiers are public configuration, not API tokens. Called only
from an explicitly dispatched, authorized GitHub Actions deployment.
"""
from pathlib import Path
from deploy_commerce import find_database_id, make_config, ROOT


def persist() -> bool:
    target=ROOT/"wrangler.toml"
    original=target.read_text(encoding="utf-8")
    verified_id=find_database_id()
    updated=make_config(verified_id)
    if updated==original:
        print("COMMERCE_DB binding is already committed/configured correctly")
        return False
    target.write_text(updated,encoding="utf-8")
    print("Persisted COMMERCE_DB binding in wrangler.toml (no credentials)")
    return True


if __name__=="__main__":
    persist()
