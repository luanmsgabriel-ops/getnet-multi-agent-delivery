"""Two-phase merchant actions (docs/adr/017): the model proposes, only the merchant confirms.

Actions:
- `anticipation`: receive future credit receivables now, for an illustrative fee.
- `terminal_service`: replacement or technician visit for a terminal that is offline or failing.

A proposal stores what was quoted and expires after 10 minutes. Confirmation happens only
through the API (`POST /actions/{id}/confirm`, scope `actions:write`, the proposal's own
merchant). There is no confirm tool, so no model output can confirm anything. Confirming twice
returns the first result. Every step is written to `actions_audit` with the state before and
after.

Proposals and the audit trail live in the state database; the receivables and terminals they
act on are the mock merchant systems (in production, calls to Getnet's APIs).
"""

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from app.data.db import Database
from app.security.auth import Principal, require_scope

# Illustrative only: not a Getnet rate. Pro rata by the days each receivable is brought forward.
ANTICIPATION_MONTHLY_RATE = 0.0199
FEE_DISCLAIMER = (
    "Valores ilustrativos: taxa fictícia de 1,99% ao mês, pro rata pelos dias antecipados "
    "(dados de demonstração, não é uma oferta real)."
)
PROPOSAL_TTL = timedelta(minutes=10)
FAILING_TERMINAL = ("offline", "error")

Kind = Literal["anticipation", "terminal_service"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS action_proposals (
    id TEXT PRIMARY KEY, merchant_id TEXT NOT NULL, tenant TEXT NOT NULL, kind TEXT NOT NULL,
    params TEXT NOT NULL, quote TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, proposed_request_id TEXT, confirmed_at TEXT,
    confirmed_request_id TEXT, idempotency_key TEXT, result TEXT
);
CREATE INDEX IF NOT EXISTS action_proposals_by_merchant
    ON action_proposals (merchant_id, created_at);
CREATE TABLE IF NOT EXISTS actions_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL, merchant_id TEXT NOT NULL,
    at TEXT NOT NULL, event TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT,
    before_state TEXT, after_state TEXT
);
CREATE INDEX IF NOT EXISTS actions_audit_by_proposal ON actions_audit (proposal_id, id);
"""


class ActionError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _brl(cents: int) -> float:
    return round(cents / 100, 2)


@dataclass(frozen=True)
class AnticipationQuote:
    receivable_ids: list[str]
    gross_cents: int
    net_cents: int  # what the merchant would receive on the original dates
    fee_cents: int  # anticipation fee (illustrative)
    first_date: str | None
    last_date: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "receivables": len(self.receivable_ids),
            "payment_dates": [self.first_date, self.last_date],
            "gross_brl": _brl(self.gross_cents),
            "net_on_original_dates_brl": _brl(self.net_cents),
            "anticipation_fee_brl": _brl(self.fee_cents),
            "net_now_brl": _brl(self.net_cents - self.fee_cents),
            "monthly_rate": ANTICIPATION_MONTHLY_RATE,
            "disclaimer": FEE_DISCLAIMER,
        }


def quote_anticipation(
    mock: Database, principal: Principal, today: date, date_from: date, date_to: date
) -> AnticipationQuote:
    """Future credit receivables of this merchant, paid in the range, still to be paid."""
    require_scope(principal, "receivables:read")
    start = max(date_from, today + timedelta(days=1))
    with mock.connect() as conn:
        rows = conn.execute(
            "SELECT r.id, r.expected_date, r.gross_cents, r.net_cents FROM receivables r "
            "JOIN sales s ON s.id = r.sale_id WHERE r.merchant_id = ? AND s.method = 'credito' "
            "AND r.status = 'previsto' AND r.expected_date BETWEEN ? AND ? "
            "ORDER BY r.expected_date, r.id",
            (principal.sub, start.isoformat(), date_to.isoformat()),
        ).fetchall()
    fee = 0
    for r in rows:
        days = (date.fromisoformat(r["expected_date"]) - today).days
        fee += round(r["net_cents"] * ANTICIPATION_MONTHLY_RATE * days / 30)
    return AnticipationQuote(
        receivable_ids=[r["id"] for r in rows],
        gross_cents=sum(r["gross_cents"] for r in rows),
        net_cents=sum(r["net_cents"] for r in rows),
        fee_cents=fee,
        first_date=rows[0]["expected_date"] if rows else None,
        last_date=rows[-1]["expected_date"] if rows else None,
    )


def terminal_for_service(mock: Database, principal: Principal, terminal_id: str) -> dict[str, Any]:
    """The merchant's own terminal, only if it is offline or failing."""
    require_scope(principal, "terminal:read")
    with mock.connect() as conn:
        row = conn.execute(
            "SELECT * FROM terminals WHERE id = ? AND merchant_id = ?", (terminal_id, principal.sub)
        ).fetchone()
    if row is None:
        raise ActionError(404, "not_found", f"Terminal {terminal_id} not found for this merchant.")
    if row["status"] not in FAILING_TERMINAL:
        raise ActionError(
            422,
            "terminal_ok",
            f"Terminal {terminal_id} is {row['status']}; service is only for offline or failing "
            "terminals. Try the troubleshooting steps first.",
        )
    return dict(row)


class ActionStore:
    def __init__(self, state: Database, mock: Database) -> None:
        self.state, self.mock = state, mock
        with state.connect() as conn:
            conn.executescript(SCHEMA)

    # -- proposals ----------------------------------------------------------------------
    def propose(
        self,
        principal: Principal,
        kind: Kind,
        params: dict[str, Any],
        quote: dict[str, Any],
        request_id: str | None,
    ) -> dict[str, Any]:
        proposal_id = f"A-{secrets.token_hex(3).upper()}"
        now = _now()
        row = {
            "id": proposal_id,
            "merchant_id": principal.sub,
            "tenant": principal.tenant,
            "kind": kind,
            "params": json.dumps(params, ensure_ascii=False),
            "quote": json.dumps(quote, ensure_ascii=False),
            "status": "proposed",
            "created_at": _iso(now),
            "expires_at": _iso(now + PROPOSAL_TTL),
            "proposed_request_id": request_id,
        }
        with self.state.connect() as conn:
            cols = ", ".join(row)
            conn.execute(
                f"INSERT INTO action_proposals ({cols}) VALUES ({', '.join('?' * len(row))})",  # noqa: S608  # nosec B608
                tuple(row.values()),
            )
        self._audit(proposal_id, principal.sub, "proposed", "assistant", request_id, None, quote)
        return {"proposal_id": proposal_id, "expires_at": row["expires_at"], "quote": quote}

    def get(self, principal: Principal, proposal_id: str) -> dict[str, Any] | None:
        with self.state.connect() as conn:
            row = conn.execute(
                "SELECT * FROM action_proposals WHERE id = ? AND merchant_id = ?",
                (proposal_id, principal.sub),
            ).fetchone()
        return None if row is None else self._public(dict(row))

    def for_merchant(self, principal: Principal, limit: int = 50) -> list[dict[str, Any]]:
        with self.state.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM action_proposals WHERE merchant_id = ? ORDER BY created_at DESC "
                "LIMIT ?",
                (principal.sub, limit),
            ).fetchall()
        return [self._public(dict(r)) for r in rows]

    def audit_trail(self, principal: Principal, proposal_id: str) -> list[dict[str, Any]]:
        with self.state.connect() as conn:
            rows = conn.execute(
                "SELECT at, event, actor, request_id, before_state, after_state FROM actions_audit "
                "WHERE proposal_id = ? AND merchant_id = ? ORDER BY id",
                (proposal_id, principal.sub),
            ).fetchall()
        return [
            {
                **{k: r[k] for k in ("at", "event", "actor", "request_id")},
                "before": json.loads(r["before_state"]) if r["before_state"] else None,
                "after": json.loads(r["after_state"]) if r["after_state"] else None,
            }
            for r in rows
        ]

    # -- confirmation (merchant only, through the API) ----------------------------------
    def confirm(
        self, principal: Principal, proposal_id: str, idempotency_key: str | None, request_id: str
    ) -> dict[str, Any]:
        require_scope(principal, "actions:write")
        current = self._row(principal, proposal_id)
        if current is None:
            raise ActionError(404, "not_found", "Proposal not found.")
        if current["status"] == "confirmed":
            return {**self._public(current), "replayed": True}
        if current["status"] != "proposed":
            raise ActionError(
                409, f"proposal_{current['status']}", f"Proposal is {current['status']}."
            )
        now = _now()
        if current["expires_at"] < _iso(now):
            self._set_status(proposal_id, "proposed", "expired")
            self._audit(proposal_id, principal.sub, "expired", "system", request_id, None, None)
            raise ActionError(410, "proposal_expired", "Proposal expired; ask the assistant again.")
        # Claim it atomically, so two concurrent confirmations execute once.
        with self.state.connect() as conn:
            claimed = conn.execute(
                "UPDATE action_proposals SET status = 'executing', idempotency_key = ?, "
                "confirmed_request_id = ? WHERE id = ? AND status = 'proposed'",
                (idempotency_key, request_id, proposal_id),
            ).rowcount
        if claimed != 1:
            again = self._row(principal, proposal_id)
            if again is not None and again["status"] == "confirmed":
                return {**self._public(again), "replayed": True}
            raise ActionError(409, "proposal_busy", "Proposal is being confirmed.")
        params = json.loads(current["params"])
        try:
            if current["kind"] == "anticipation":
                before, after, result = self._run_anticipation(principal, params)
            else:
                before, after, result = self._run_terminal_service(principal, params, proposal_id)
        except ActionError as exc:
            self._set_status(proposal_id, "executing", "failed")
            self._audit(
                proposal_id,
                principal.sub,
                "failed",
                principal.sub,
                request_id,
                None,
                {"error": exc.code},
            )
            raise
        with self.state.connect() as conn:
            conn.execute(
                "UPDATE action_proposals SET status = 'confirmed', confirmed_at = ?, result = ? "
                "WHERE id = ?",
                (_iso(_now()), json.dumps(result, ensure_ascii=False), proposal_id),
            )
        self._audit(
            proposal_id, principal.sub, "confirmed", principal.sub, request_id, before, after
        )
        confirmed = self._row(principal, proposal_id)
        assert confirmed is not None
        return {**self._public(confirmed), "replayed": False}

    def _run_anticipation(
        self, principal: Principal, params: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        ids: list[str] = params["receivable_ids"]
        marks = ", ".join("?" * len(ids))
        with self.mock.connect() as conn:
            changed = conn.execute(
                f"UPDATE receivables SET status = 'antecipado' WHERE merchant_id = ? AND "  # noqa: S608  # nosec B608
                f"status = 'previsto' AND id IN ({marks})",
                (principal.sub, *ids),
            ).rowcount
            if changed != len(ids):  # raising inside the block rolls the update back
                raise ActionError(
                    409,
                    "quote_stale",
                    "Some receivables changed since the simulation; simulate again.",
                )
        before = {"receivables": len(ids), "status": "previsto"}
        after = {"receivables": len(ids), "status": "antecipado"}
        result = {
            "anticipated_receivables": len(ids),
            "net_now_brl": params["net_now_brl"],
            "credited_to": "settlement account on file",
            "disclaimer": FEE_DISCLAIMER,
        }
        return before, after, result

    def _run_terminal_service(
        self, principal: Principal, params: dict[str, Any], proposal_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        terminal = terminal_for_service(self.mock, principal, params["terminal_id"])
        protocol = f"OS-{proposal_id[2:]}"
        before = {"terminal_id": terminal["id"], "status": terminal["status"]}
        after = {**before, "service": params["service"], "protocol": protocol}
        result = {
            "protocol": protocol,
            "terminal_id": terminal["id"],
            "service": params["service"],
            "next_step": "The technical team contacts the merchant to schedule it.",
        }
        return before, after, result

    # -- helpers ------------------------------------------------------------------------
    def _row(self, principal: Principal, proposal_id: str) -> dict[str, Any] | None:
        with self.state.connect() as conn:
            row = conn.execute(
                "SELECT * FROM action_proposals WHERE id = ? AND merchant_id = ?",
                (proposal_id, principal.sub),
            ).fetchone()
        return None if row is None else dict(row)

    def _set_status(self, proposal_id: str, old: str, new: str) -> None:
        with self.state.connect() as conn:
            conn.execute(
                "UPDATE action_proposals SET status = ? WHERE id = ? AND status = ?",
                (new, proposal_id, old),
            )

    def _audit(
        self,
        proposal_id: str,
        merchant_id: str,
        event: str,
        actor: str,
        request_id: str | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        with self.state.connect() as conn:
            conn.execute(
                "INSERT INTO actions_audit (proposal_id, merchant_id, at, event, actor, "
                "request_id, before_state, after_state) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal_id,
                    merchant_id,
                    _iso(_now()),
                    event,
                    actor,
                    request_id,
                    json.dumps(before, ensure_ascii=False) if before is not None else None,
                    json.dumps(after, ensure_ascii=False) if after is not None else None,
                ),
            )

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        params = json.loads(row["params"])
        params.pop("receivable_ids", None)  # internal ids stay server-side
        return {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "params": params,
            "quote": json.loads(row["quote"]),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "confirmed_at": row["confirmed_at"],
            "result": json.loads(row["result"]) if row["result"] else None,
        }
