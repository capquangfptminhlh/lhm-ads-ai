-- Gmail-bound plans: normalized Gmail key, sellable plans, payment codes,
-- one active license per customer, device labels and admin notes.
-- Subscription metadata only; NEVER Ads credentials, account IDs or reports.

ALTER TABLE customers ADD COLUMN email_key TEXT;
ALTER TABLE customers ADD COLUMN picture_url TEXT;
ALTER TABLE customers ADD COLUMN updated_at TEXT;
-- Gmail ignores dots and "+tag" in the local part and treats googlemail.com
-- as gmail.com. Must match normalizeEmail() in workers/ads-api/src/identity.js.
UPDATE customers SET email_key=CASE
  WHEN substr(lower(trim(email)),instr(lower(trim(email)),'@')+1) IN ('gmail.com','googlemail.com')
  THEN replace(CASE WHEN instr(lower(trim(email)),'+')>0
                    THEN substr(lower(trim(email)),1,instr(lower(trim(email)),'+')-1)
                    ELSE substr(lower(trim(email)),1,instr(lower(trim(email)),'@')-1) END,'.','')||'@gmail.com'
  ELSE lower(trim(email)) END
WHERE email_key IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_email_key ON customers(email_key);

CREATE TABLE IF NOT EXISTS plans (
  code TEXT PRIMARY KEY CHECK(length(code) BETWEEN 2 AND 40),
  name TEXT NOT NULL,
  seat_limit INTEGER NOT NULL CHECK(seat_limit BETWEEN 1 AND 20),
  months INTEGER NOT NULL CHECK(months BETWEEN 1 AND 36),
  price_vnd INTEGER NOT NULL CHECK(price_vnd >= 0),
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  sort INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT
);
-- Pilot prices from docs/sales/BANG-GIA-MAU.md. Team stays off until priced.
INSERT OR IGNORE INTO plans(code,name,seat_limit,months,price_vnd,active,sort) VALUES
  ('personal-1m','Cá nhân · 1 tháng',2,1,499000,1,10),
  ('personal-6m','Cá nhân · 6 tháng',2,6,2545000,1,20),
  ('personal-12m','Cá nhân · 12 tháng',2,12,4491000,1,30),
  ('team-1m','Team · 1 tháng',5,1,0,0,40);

ALTER TABLE orders ADD COLUMN plan_code TEXT;
ALTER TABLE orders ADD COLUMN payment_code TEXT;
ALTER TABLE orders ADD COLUMN expires_at TEXT;
ALTER TABLE orders ADD COLUMN days INTEGER CHECK(days IS NULL OR days BETWEEN 1 AND 1100);
ALTER TABLE orders ADD COLUMN source TEXT NOT NULL DEFAULT 'admin'
  CHECK(source IN ('admin','self_service','admin_grant','pilot_migration'));
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_payment_code ON orders(payment_code) WHERE payment_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status,created_at);

ALTER TABLE licenses ADD COLUMN plan_code TEXT;
-- A Gmail holds at most one active plan; renewals extend it.
CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_one_active ON licenses(customer_id) WHERE status='active';

ALTER TABLE license_seats ADD COLUMN platform TEXT CHECK(platform IS NULL OR platform IN ('pwa','windows'));
ALTER TABLE license_seats ADD COLUMN device_label TEXT;
ALTER TABLE license_seats ADD COLUMN first_seen_at TEXT;

ALTER TABLE admin_audit ADD COLUMN detail TEXT;

CREATE TABLE IF NOT EXISTS customer_notes (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  actor TEXT NOT NULL,
  note TEXT NOT NULL CHECK(length(note) BETWEEN 1 AND 1000),
  at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_customer_notes_customer ON customer_notes(customer_id,at);
