-- Every paid order can issue or extend a license at most once.
-- D1 batch operations insert into this table atomically with the license mutation.
CREATE TABLE IF NOT EXISTS license_fulfillments (
 order_id TEXT PRIMARY KEY REFERENCES orders(id),
 license_id TEXT NOT NULL REFERENCES licenses(id),
 action TEXT NOT NULL CHECK (action IN ('issue','renew')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_license_fulfillments_license ON license_fulfillments(license_id);
-- Backfill keys created before this migration; prevents reusing issuance orders for renewals.
INSERT OR IGNORE INTO license_fulfillments(order_id,license_id,action,created_at)
 SELECT l.id,l.id,'issue',l.created_at
 FROM licenses l JOIN orders o ON o.id=l.id;
