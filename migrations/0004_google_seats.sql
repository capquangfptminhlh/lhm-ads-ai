-- Subscription metadata only; no Google Ads / Meta credentials, campaign IDs, or reports.
-- Applying this migration is required BEFORE enabling Google sign-in.
ALTER TABLE customers ADD COLUMN google_sub TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_google_sub ON customers(google_sub);
ALTER TABLE orders ADD COLUMN seat_limit INTEGER NOT NULL DEFAULT 1 CHECK(seat_limit BETWEEN 1 AND 20);
ALTER TABLE licenses ADD COLUMN seat_limit INTEGER NOT NULL DEFAULT 1 CHECK(seat_limit BETWEEN 1 AND 20);
CREATE TABLE IF NOT EXISTS license_seats (
  license_id TEXT NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
  client_hash TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (license_id, client_hash)
);
CREATE INDEX IF NOT EXISTS idx_license_seats_recent ON license_seats(license_id,last_seen_at);
