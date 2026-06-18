CREATE TABLE IF NOT EXISTS authorized_users (
    chat_id TEXT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    secret TEXT,
    created_at TEXT NOT NULL,
    created_by_chat_id TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_authorized_users_active
    ON authorized_users(is_active);

CREATE INDEX IF NOT EXISTS idx_authorized_users_secret
    ON authorized_users(secret);

CREATE TABLE IF NOT EXISTS access_passwords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    secret TEXT NOT NULL,
    secret_norm TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    created_by_chat_id TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    used_by_chat_id TEXT,
    used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_access_passwords_norm
    ON access_passwords(secret_norm);

CREATE INDEX IF NOT EXISTS idx_access_passwords_state
    ON access_passwords(is_active, used_by_chat_id);
