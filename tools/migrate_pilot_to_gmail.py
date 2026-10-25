"""Move pilot customers (offline per-machine licenses) to Gmail-bound plans.

The seller's offline ledger (tools/vendor_ledger.py) knows each customer_ref and
license expiry but no Gmail. The seller collects each customer's Gmail into a
CSV with columns `customer_ref,gmail`. This tool joins the two and prints, for
each customer with time left, the grant to make: Gmail, remaining days, a
reference. Nothing is sent anywhere.

  python tools/migrate_pilot_to_gmail.py --map gmails.csv               # preview
  python tools/migrate_pilot_to_gmail.py --map gmails.csv --out grants.csv

Paste grants.csv into Admin → "Cấp gói theo Gmail" → "Nhập danh sách chuyển khách
pilot". The Admin page grants each line with the remaining days (source
pilot_migration), using the admin's own Cloudflare Access session.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vendor_ledger import connect, default_database  # noqa: E402

EMAIL = re.compile(r"^[^\s@,]+@[^\s@,]+\.[^\s@,]+$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")


def read_map(text: str) -> list[tuple[str, str]]:
    rows = []
    for n, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not row or not "".join(row).strip() or row[0].strip().lower() == "customer_ref":
            continue
        if len(row) < 2:
            raise ValueError(f"Line {n}: expected customer_ref,gmail")
        ref, gmail = row[0].strip(), row[1].strip()
        if not REF.fullmatch(ref):
            raise ValueError(f"Line {n}: invalid customer_ref {ref!r}")
        if not EMAIL.fullmatch(gmail):
            raise ValueError(f"Line {n}: invalid Gmail {gmail!r}")
        rows.append((ref, gmail))
    refs = [r for r, _ in rows]
    if len(refs) != len(set(refs)):
        raise ValueError("A customer_ref appears twice in the map")
    return rows


def plan(db: sqlite3.Connection, mapping: list[tuple[str, str]], now: float) -> list[dict]:
    out = []
    for ref, gmail in mapping:
        row = db.execute("SELECT license_id,expires_at FROM licenses WHERE customer_ref=? "
                         "ORDER BY expires_at DESC,recorded_at DESC LIMIT 1", (ref,)).fetchone()
        if row is None:
            out.append({"customer_ref": ref, "gmail": gmail, "days": 0, "status": "no_license"})
            continue
        left = row["expires_at"] - now
        days = math.ceil(left / 86400) if left > 0 else 0
        expires = datetime.fromtimestamp(row["expires_at"], timezone.utc).strftime("%Y-%m-%d")
        out.append({"customer_ref": ref, "gmail": gmail, "days": days,
                    "status": "grant" if days > 0 else "expired",
                    "reference": f"PILOT-{ref}"[:120],
                    "note": f"Pilot license {row['license_id']} expires {expires}"[:500]})
    return out


def to_csv(entries: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["gmail", "days", "reference", "note"])
    for e in entries:
        if e["status"] == "grant":
            writer.writerow([e["gmail"], e["days"], e["reference"], e["note"]])
    return buf.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--map", required=True, help="CSV with customer_ref,gmail")
    ap.add_argument("--ledger", default=None, help="vendor ledger SQLite (default: the seller's ledger)")
    ap.add_argument("--out", help="write grants CSV here for the Admin bulk import")
    args = ap.parse_args(argv)
    mapping = read_map(Path(args.map).read_text(encoding="utf-8-sig"))
    db = connect(args.ledger or default_database())
    entries = plan(db, mapping, time.time())
    for e in entries:
        print(f"{e['status']:<10} {e['customer_ref']:<20} {e['gmail']:<36} {e['days']:>4} days")
    granted = sum(e["status"] == "grant" for e in entries)
    print(f"{granted} to grant, {len(entries) - granted} skipped (expired or no license).")
    if args.out:
        Path(args.out).write_text(to_csv(entries), encoding="utf-8", newline="\n")
        print(f"Wrote {args.out}. Paste it into Admin > Cấp gói theo Gmail > Nhập danh sách chuyển khách pilot.")
    else:
        print("Preview only. Add --out grants.csv to write the file for the Admin page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
