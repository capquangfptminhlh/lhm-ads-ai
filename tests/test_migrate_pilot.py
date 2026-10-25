"""Pilot -> Gmail migration preview: remaining days per customer, nothing sent."""
import sqlite3
import time

import pytest

from tools.migrate_pilot_to_gmail import plan, read_map, to_csv
from tools.vendor_ledger import connect


def ledger(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    now = int(time.time())
    for ref, device, expires in (("KH001", "a" * 32, now + 12 * 86400 - 60), ("KH002", "b" * 32, now - 86400)):
        db.execute("INSERT INTO customers(customer_ref,device,created_at) VALUES(?,?,?)", (ref, device, now))
        db.execute("INSERT INTO licenses(license_id,customer_ref,device,plan,issued_at,expires_at,signature_sha256,"
                   "payment_status,receipt_ref,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   ("lic-" + ref, ref, device, "monthly", now - 86400, expires, "0" * 64, "confirmed", None, now))
    db.execute("INSERT INTO customers(customer_ref,device,created_at) VALUES('KH003',?,?)", ("c" * 32, now))
    db.commit()
    return db


def test_remaining_days_and_skips(tmp_path):
    db = ledger(tmp_path)
    mapping = read_map("customer_ref,gmail\nKH001,Khach.Mot@gmail.com\nKH002,hai@gmail.com\nKH003,ba@gmail.com\n")
    entries = {e["customer_ref"]: e for e in plan(db, mapping, time.time())}
    assert entries["KH001"]["status"] == "grant" and entries["KH001"]["days"] == 12
    assert entries["KH002"]["status"] == "expired"
    assert entries["KH003"]["status"] == "no_license"
    out = to_csv(entries.values())
    assert out.splitlines() == ["gmail,days,reference,note",
                                f"Khach.Mot@gmail.com,12,PILOT-KH001,Pilot license lic-KH001 expires {entries['KH001']['note'][-10:]}"]


def test_map_rejects_bad_rows():
    with pytest.raises(ValueError):
        read_map("KH001,not-an-email\n")
    with pytest.raises(ValueError):
        read_map("KH001,a@gmail.com\nKH001,b@gmail.com\n")
