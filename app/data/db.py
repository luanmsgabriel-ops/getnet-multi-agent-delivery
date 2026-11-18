"""SQLite access for the mock merchant data, tokens revocation and app metadata."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS revoked_tokens (jti TEXT PRIMARY KEY, revoked_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS feedback (
    request_id TEXT NOT NULL, merchant_id TEXT NOT NULL, rating TEXT NOT NULL, comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS merchants (
    id TEXT PRIMARY KEY,
    tenant TEXT NOT NULL,
    trade_name TEXT NOT NULL,
    settlement_account TEXT NOT NULL,
    credit_settlement_days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS terminals (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchants(id),
    model TEXT NOT NULL,
    connection TEXT NOT NULL,
    status TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    firmware TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchants(id),
    terminal_id TEXT NOT NULL REFERENCES terminals(id),
    sold_at TEXT NOT NULL,
    method TEXT NOT NULL,
    brand TEXT NOT NULL,
    card_last4 TEXT,
    amount_cents INTEGER NOT NULL,
    installments INTEGER NOT NULL,
    status TEXT NOT NULL,
    decline_code TEXT
);
CREATE INDEX IF NOT EXISTS ix_sales_merchant_date ON sales(merchant_id, sold_at);

CREATE TABLE IF NOT EXISTS receivables (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchants(id),
    sale_id TEXT NOT NULL REFERENCES sales(id),
    installment INTEGER NOT NULL,
    expected_date TEXT NOT NULL,
    gross_cents INTEGER NOT NULL,
    fee_cents INTEGER NOT NULL,
    net_cents INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_receivables_merchant_date ON receivables(merchant_id, expected_date);

CREATE TABLE IF NOT EXISTS decline_codes (
    code TEXT PRIMARY KEY,
    meaning TEXT NOT NULL,
    merchant_action TEXT NOT NULL,
    retry_allowed INTEGER NOT NULL
);
"""

MOCK_TABLES = ("receivables", "sales", "terminals", "merchants", "decline_codes")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def get_meta(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def is_revoked(self, jti: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)).fetchone()
        return row is not None

    def revoke(self, jti: str, revoked_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO revoked_tokens(jti, revoked_at) VALUES (?, ?)",
                (jti, revoked_at),
            )

    def add_feedback(
        self, request_id: str, merchant_id: str, rating: str, comment: str | None
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO feedback (request_id, merchant_id, rating, comment) "
                "VALUES (?, ?, ?, ?)",
                (request_id, merchant_id, rating, comment),
            )
