"""D1 schema and subscription-order transaction regression tests (SQLite semantics)."""
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AdminCommerceSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("000[12]_*.sql")):
            self.db.executescript(path.read_text(encoding="utf-8"))
        self.db.execute(
            "INSERT INTO customers(id,name,email) VALUES(?,?,?)",
            ("customer-a", "Customer A", "a@example.invalid"),
        )
        for order in ("order-a", "order-b", "order-c"):
            self.db.execute(
                "INSERT INTO orders(id,customer_id,months,amount_vnd,status)"
                " VALUES(?,?,?,?,?)",
                (order, "customer-a", 1, 499000, "paid"),
            )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _issue(self, order_id):
        with self.db:
            self.db.execute(
                "INSERT INTO licenses(id,customer_id,key_hash,key_hint,expires_at)"
                " VALUES(?,?,?,?,?)",
                (order_id, "customer-a", "hash-" + order_id, "1234ABCD", "2099-11-24T08:00:00.000Z"),
            )
            self.db.execute(
                "INSERT INTO license_fulfillments(order_id,license_id,action)"
                " VALUES(?,?,'issue')", (order_id, order_id)
            )

    def _renew(self, order_id, license_id):
        with self.db:
            self.db.execute(
                "INSERT INTO license_fulfillments(order_id,license_id,action)"
                " VALUES(?,?,'renew')", (order_id, license_id)
            )
            self.db.execute(
                """UPDATE licenses SET
                    expires_at=strftime('%Y-%m-%dT%H:%M:%fZ',
                    datetime(CASE WHEN julianday(expires_at)>julianday('now')
                    THEN expires_at ELSE 'now' END, '+' || ? || ' months')),
                    status='active',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (1, license_id)
            )

    def test_one_order_only_once(self):
        self._issue("order-a")
        with self.assertRaises(sqlite3.IntegrityError):
            self._renew("order-a", "order-a")
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM license_fulfillments").fetchone()[0], 1
        )

    def test_two_distinct_renewals_accumulate(self):
        self._issue("order-a")
        self._renew("order-b", "order-a")
        self._renew("order-c", "order-a")
        self.assertEqual(
            self.db.execute("SELECT expires_at FROM licenses WHERE id='order-a'").fetchone()[0],
            "2100-01-24T08:00:00.000Z"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self._renew("order-b", "order-a")
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM license_fulfillments").fetchone()[0], 3
        )

    def test_failed_batch_rolls_back_new_fulfillment(self):
        self._issue("order-a")
        before = self.db.execute(
            "SELECT expires_at FROM licenses WHERE id='order-a'"
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db:
                self.db.execute(
                    "INSERT INTO license_fulfillments(order_id,license_id,action)"
                    " VALUES(?,?,'renew')", ("order-b", "order-a")
                )
                self.db.execute(
                    "INSERT INTO license_fulfillments(order_id,license_id,action)"
                    " VALUES(?,?,'renew')", ("order-b", "order-a")
                )
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM license_fulfillments").fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT expires_at FROM licenses WHERE id='order-a'").fetchone()[0], before)

    def test_foreign_keys_reject_unknown_customers(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO orders(id,customer_id,months,amount_vnd)"
                " VALUES('bad','no-such-customer',1,499000)"
            )


if __name__ == "__main__":
    unittest.main()
