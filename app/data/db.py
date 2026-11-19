"""Database access: SQLite for the mock merchant data, SQLite or Postgres for app state.

The mock merchant tables stand in for Getnet's own systems and stay in a local SQLite file.
App state (handoff queue, events, tickets, merchant memory, spend ledger, revoked tokens,
feedback) lives in the same file by default, or in Postgres when STATE_DATABASE_URL is set, so
several API replicas share it (docs/adr/014). Both backends take the same SQL: a thin adapter
translates the few dialect differences (placeholders, INSERT OR IGNORE, AUTOINCREMENT).
"""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

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

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS revoked_tokens (jti TEXT PRIMARY KEY, revoked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (
    request_id TEXT NOT NULL, merchant_id TEXT NOT NULL, rating TEXT NOT NULL, comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

DB_ERRORS: tuple[type[Exception], ...] = (sqlite3.Error, psycopg.Error)


def to_postgres(sql: str) -> str:
    """Translate the SQLite dialect used in this project to Postgres."""
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    if re.match(r"\s*INSERT OR IGNORE", sql, re.IGNORECASE):
        sql = re.sub(r"INSERT OR IGNORE", "INSERT", sql, count=1, flags=re.IGNORECASE)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql.replace("?", "%s")


class PgConnection:
    """sqlite3-like facade over a psycopg connection (execute, executescript, row["col"])."""

    def __init__(self, conn: psycopg.Connection[dict[str, Any]]) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any:
        return self._conn.execute(to_postgres(sql), tuple(params))

    def executescript(self, script: str) -> None:
        for statement in (s.strip() for s in script.split(";")):
            if statement:
                self._conn.execute(to_postgres(statement))


class Database:
    def __init__(self, target: Path | str) -> None:
        self.url = str(target) if str(target).startswith(("postgres://", "postgresql://")) else None
        self.path = Path(target) if self.url is None else Path()

    @property
    def is_postgres(self) -> bool:
        return self.url is not None

    def init(self) -> None:
        """Mock data and state tables (SQLite file)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def init_state(self) -> None:
        """State tables only (used when state lives in Postgres)."""
        if not self.is_postgres:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(STATE_SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.url is not None:
            with psycopg.connect(self.url, row_factory=dict_row) as pg:
                yield PgConnection(pg)  # commits on success, rolls back on error
            return
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
        except DB_ERRORS:
            return False

    def get_meta(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, conn: Any, key: str, value: str) -> None:
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
