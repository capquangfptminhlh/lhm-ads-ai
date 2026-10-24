-- Customer PWA authentication; contains no Ads API credentials or report data.
CREATE TABLE IF NOT EXISTS customer_auth (
 customer_id TEXT PRIMARY KEY REFERENCES customers(id),
 password_salt TEXT NOT NULL,
 password_hash TEXT NOT NULL,
 failed_attempts INTEGER NOT NULL DEFAULT 0,
 locked_until TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS customer_sessions (
 token_hash TEXT PRIMARY KEY,
 customer_id TEXT NOT NULL REFERENCES customers(id),
 expires_at TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_customer_sessions_customer ON customer_sessions(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_sessions_expiry ON customer_sessions(expires_at);
