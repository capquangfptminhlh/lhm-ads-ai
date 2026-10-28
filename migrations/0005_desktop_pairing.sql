-- Browser-verified desktop pairing, no Ads provider credentials.
CREATE TABLE IF NOT EXISTS desktop_pairings (
  id TEXT PRIMARY KEY,
  verifier_hash TEXT NOT NULL,
  display_code TEXT NOT NULL,
  customer_id TEXT REFERENCES customers(id),
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_desktop_pairings_expire ON desktop_pairings(expires_at);
CREATE TABLE IF NOT EXISTS desktop_sessions (
  token_hash TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_desktop_sessions_expire ON desktop_sessions(expires_at);
