"""SQLite persistence. Each helper enforces tenant scope in the query layer."""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = lambda: os.environ.get("DB_PATH", "./data/lhm-ads.sqlite3")

@contextmanager
def connection():
    path = Path(DB_PATH())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connection() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL DEFAULT 'main',
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin','operator','reader')),
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            csrf TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            scope TEXT NOT NULL CHECK (scope IN ('reader','operator')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('demo','meta','google','tiktok','openai')),
            label TEXT NOT NULL,
            external_id TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'VND',
            token_ciphertext TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (org_id, platform, external_id)
        );
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            action_type TEXT NOT NULL CHECK(action_type IN ('pause_campaign')),
            target_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','executing','completed','rejected','failed')),
            requested_by INTEGER NOT NULL REFERENCES users(id),
            reviewed_by INTEGER REFERENCES users(id),
            failure_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            actor_id INTEGER,
            event TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_accounts_org ON accounts(org_id);
        CREATE INDEX IF NOT EXISTS idx_actions_org ON actions(org_id, status);
        CREATE INDEX IF NOT EXISTS idx_audit_org ON audit(org_id, id DESC);
        """)


def audit(db, ident, event, detail):
    # NEVER pass credentials, tokens, raw provider responses, or request bodies here.
    db.execute("INSERT INTO audit(org_id, actor_id, event, detail) VALUES(?,?,?,?)",
               (ident['org_id'], ident['id'], event, detail[:220]))
