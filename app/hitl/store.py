"""Persistence for human handoffs, ticket proposals and merchant-facing session events."""

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.data.db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, merchant_id TEXT NOT NULL, scopes TEXT NOT NULL,
    session_id TEXT NOT NULL, thread_id TEXT NOT NULL, reason TEXT NOT NULL,
    priority TEXT NOT NULL, summary TEXT NOT NULL, language TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, operator TEXT, operator_action TEXT,
    operator_message TEXT, replied_at TEXT, final_answer TEXT
);
CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id TEXT NOT NULL, session_id TEXT NOT NULL,
    type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY, merchant_id TEXT NOT NULL, topic TEXT NOT NULL, summary TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
    confirmed_at TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class HitlStore:
    def __init__(self, db: Database) -> None:
        self.db = db
        with db.connect() as conn:
            conn.executescript(SCHEMA)

    # -- handoffs ------------------------------------------------------------------------
    def create_handoff(self, **fields: str) -> str:
        handoff_id = f"H-{secrets.token_hex(3).upper()}"
        row = {"id": handoff_id, "status": "pending", "created_at": _now(), **fields}
        cols = ", ".join(row)
        with self.db.connect() as conn:
            conn.execute(
                f"INSERT INTO handoffs ({cols}) VALUES ({', '.join('?' * len(row))})",  # noqa: S608  # nosec B608
                tuple(row.values()),
            )
        return handoff_id

    def handoff(self, handoff_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone()
        return None if row is None else dict(row)

    def handoffs(self, status: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM handoffs", tuple[str, ...]()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY created_at", args)]

    def pending_for(self, merchant_id: str, session_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM handoffs WHERE merchant_id = ? AND session_id = ? AND status IN "
                "('pending', 'replying') ORDER BY created_at DESC LIMIT 1",
                (merchant_id, session_id),
            ).fetchone()
        return None if row is None else dict(row)

    def claim_reply(self, handoff_id: str, operator: str, action: str, message: str) -> bool:
        """Atomically move pending -> replying; False if already answered (idempotency)."""
        with self.db.connect() as conn:
            cur = conn.execute(
                "UPDATE handoffs SET status = 'replying', operator = ?, operator_action = ?, "
                "operator_message = ?, replied_at = ? WHERE id = ? AND status = 'pending'",
                (operator, action, message, _now(), handoff_id),
            )
        return bool(cur.rowcount == 1)

    def resolve(self, handoff_id: str, final_answer: str, status: str = "resolved") -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE handoffs SET status = ?, final_answer = ? WHERE id = ?",
                (status, final_answer, handoff_id),
            )

    def release(self, handoff_id: str) -> None:
        """Return a claimed handoff to the queue after a failed resume."""
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE handoffs SET status = 'pending' WHERE id = ? AND status = 'replying'",
                (handoff_id,),
            )

    # -- merchant events (SSE) -----------------------------------------------------------
    def add_event(
        self, merchant_id: str, session_id: str, kind: str, payload: dict[str, Any]
    ) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "INSERT INTO session_events (merchant_id, session_id, type, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?) RETURNING id",
                (merchant_id, session_id, kind, json.dumps(payload, ensure_ascii=False), _now()),
            ).fetchone()
        return int(row["id"])

    def events_after(self, merchant_id: str, session_id: str, after: int) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM session_events WHERE merchant_id = ? AND session_id = ? AND id > ? "
                "ORDER BY id",
                (merchant_id, session_id, after),
            ).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    # -- tickets (two-phase write) -------------------------------------------------------
    def propose_ticket(self, merchant_id: str, topic: str, summary: str) -> dict[str, Any]:
        ticket_id = f"T-{secrets.token_hex(3).upper()}"
        expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat(timespec="seconds")
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO tickets VALUES (?, ?, ?, ?, 'proposed', ?, ?, NULL)",
                (ticket_id, merchant_id, topic, summary, _now(), expires),
            )
        return {"proposal_id": ticket_id, "expires_at": expires}

    def confirm_ticket(self, merchant_id: str, ticket_id: str) -> dict[str, Any] | None:
        """Idempotent: confirming an already-open ticket returns it unchanged."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE id = ? AND merchant_id = ?", (ticket_id, merchant_id)
            ).fetchone()
            if row is None:
                return None
            if row["status"] == "proposed":
                if row["expires_at"] < _now():
                    conn.execute("UPDATE tickets SET status = 'expired' WHERE id = ?", (ticket_id,))
                else:
                    conn.execute(
                        "UPDATE tickets SET status = 'open', confirmed_at = ? WHERE id = ?",
                        (_now(), ticket_id),
                    )
            row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return dict(row)

    def tickets(self, merchant_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE merchant_id = ? AND status != "
                "'proposed' ORDER BY created_at DESC",
                (merchant_id,),
            ).fetchall()
        return [dict(r) for r in rows]
