"""Persistence for human handoffs (queue, deadlines, audit trail), ticket proposals and
merchant-facing session events."""

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
CREATE TABLE IF NOT EXISTS handoff_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, handoff_id TEXT NOT NULL, at TEXT NOT NULL,
    kind TEXT NOT NULL, actor TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS handoff_audit_by_handoff ON handoff_audit (handoff_id, id);
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY, merchant_id TEXT NOT NULL, topic TEXT NOT NULL, summary TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
    confirmed_at TEXT
);
"""


# Minutes an operator has to answer, by the priority the handoff was opened with (DECISIONS.md).
# A breach raises the priority to "urgent" once and sends a reminder.
SLA_MINUTES = {"high": 15, "normal": 60}
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def due_at(handoff: dict[str, Any]) -> str | None:
    """Answer deadline; None once the handoff was raised to urgent (its deadline has passed)."""
    minutes = SLA_MINUTES.get(handoff["priority"])
    if minutes is None:
        return None
    opened = datetime.fromisoformat(handoff["created_at"])
    return (opened + timedelta(minutes=minutes)).isoformat(timespec="seconds")


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
        """The queue: most urgent first, then oldest first."""
        sql, args = "SELECT * FROM handoffs", tuple[str, ...]()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        with self.db.connect() as conn:
            rows = [dict(r) for r in conn.execute(sql + " ORDER BY created_at", args)]
        rows.sort(key=lambda h: PRIORITY_RANK.get(h["priority"], 9))  # stable: keeps age order
        return rows

    def overdue(self, now: datetime) -> list[dict[str, Any]]:
        """Pending handoffs past their deadline that have not been escalated yet."""
        late = []
        for h in self.handoffs("pending"):
            due = due_at(h)
            if due is not None and datetime.fromisoformat(due) < now:
                late.append(h)
        return late

    def mark_breached(self, handoff_id: str) -> bool:
        """Raise to urgent; True only for the caller that did it (one reminder per handoff,
        even with several replicas sweeping)."""
        with self.db.connect() as conn:
            cur = conn.execute(
                "UPDATE handoffs SET priority = 'urgent' WHERE id = ? AND status = 'pending' "
                "AND priority != 'urgent'",
                (handoff_id,),
            )
        return bool(cur.rowcount == 1)

    # -- audit trail ---------------------------------------------------------------------
    def audit(self, handoff_id: str, kind: str, actor: str, **detail: Any) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO handoff_audit (handoff_id, at, kind, actor, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (handoff_id, _now(), kind, actor, json.dumps(detail, ensure_ascii=False)),
            )

    def audit_trail(self, handoff_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT at, kind, actor, detail FROM handoff_audit WHERE handoff_id = ? "
                "ORDER BY id",
                (handoff_id,),
            ).fetchall()
        return [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]

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
