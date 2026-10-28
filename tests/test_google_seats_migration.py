"""Test the real D1-compatible subscription schema and isolated seat slots."""
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class GoogleSeatMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        for path in sorted((ROOT/"migrations").glob("000[1-4]_*.sql")):
            self.db.executescript(path.read_text(encoding="utf-8"))

    def tearDown(self):
        self.db.close()

    def test_google_id_is_unique_and_ads_data_is_not_a_column(self):
        self.db.execute("INSERT INTO customers(id,name,email,google_sub) VALUES('a','A','a@example.com','google-sub-a')")
        self.db.execute("INSERT INTO customers(id,name,email,google_sub) VALUES('b','B','b@example.com','google-sub-b')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE customers SET google_sub='google-sub-a' WHERE id='b'")
        self.assertFalse({"access_token","refresh_token","campaigns","account_id"}.intersection({
            r[1] for r in self.db.execute("PRAGMA table_info(customers)")
        }))

    def test_same_client_hash_per_license_not_global(self):
        self.db.execute("INSERT INTO customers(id,name,email) VALUES('a','A','a@example.com')")
        self.db.execute("INSERT INTO customers(id,name,email) VALUES('b','B','b@example.com')")
        for customer in ('a','b'):
            self.db.execute("INSERT INTO licenses(id,customer_id,key_hash,key_hint,expires_at,seat_limit) VALUES(?,?,?,?,?,?)",
             (customer,customer,'hash-'+customer,'hint','2030-01-01T00:00:00Z',3))
            self.db.execute("INSERT INTO license_seats(license_id,client_hash,last_seen_at) VALUES(?,?,?)",
             (customer,'same-client-hash','2026-10-25T00:00:00Z'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO license_seats(license_id,client_hash,last_seen_at) VALUES('a','same-client-hash','2026-10-25T00:00:00Z')")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM license_seats").fetchone()[0],2)

    def test_atomic_capacity_and_expiry(self):
        self.db.execute("INSERT INTO customers(id,name,email) VALUES('a','A','a@example.com')")
        self.db.execute("INSERT INTO licenses(id,customer_id,key_hash,key_hint,expires_at,seat_limit) VALUES('l','a','h','hint','2030-01-01T00:00:00Z',3)")
        for name in ('one','two','three','four'):
            self.db.execute("INSERT INTO license_seats(license_id,client_hash,last_seen_at) SELECT 'l',?,? WHERE (SELECT COUNT(*) FROM license_seats WHERE license_id='l')<3",
             (name,'2026-10-25T09:00:00Z'))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM license_seats").fetchone()[0],3)
        self.db.execute("DELETE FROM license_seats WHERE license_id='l' AND client_hash='one'")
        self.db.execute("INSERT INTO license_seats(license_id,client_hash,last_seen_at) SELECT 'l','four','2026-10-25T09:30:00Z' WHERE (SELECT COUNT(*) FROM license_seats WHERE license_id='l')<3")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM license_seats").fetchone()[0],3)

if __name__=="__main__":
    unittest.main()
