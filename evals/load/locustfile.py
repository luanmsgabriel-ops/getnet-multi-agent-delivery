"""Locust users for `make load` (PRD 09): real conversations over POST /chat/stream.

Each user picks a conversation from the 10 challenge scenarios and the 40 dev cases, opens a
new session and sends its turns, pausing 5 s between turns. Users are spread over the three
mock merchants, so the per-merchant rate limit is not what is being measured. Two timings per
turn: the first server-sent event (the user sees progress) and the final verified answer.

Tokens come from the environment (LOAD_TOKENS: comma-separated merchant tokens, in the order
cliente1988, cliente2000, cliente3000); evals/load/run.py issues them from the OIDC provider.
"""

import itertools
import json
import os
import random
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from locust import HttpUser, constant, events, task

ROOT = Path(__file__).resolve().parents[1]
MERCHANTS = ("cliente1988", "cliente2000", "cliente3000")
TOKENS = [t for t in os.environ.get("LOAD_TOKENS", "").split(",") if t]
TURNS_FILE = Path(os.environ.get("LOAD_TURNS_FILE", "load_turns.jsonl"))
_lock = threading.Lock()
_next_merchant = itertools.count()
# Status steps that mean a specialist started real work (not just "analyzing").
WORK_STEPS = {"knowledge", "support", "escalation"}


def _conversations() -> list[dict[str, Any]]:
    out = []
    for name in ("original.jsonl", "dev.jsonl"):
        for line in (ROOT / "datasets" / name).read_text("utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            turns = case.get("turns") or [case["message"]]
            tags = case.get("tags") or ["other"]
            out.append({"id": case["id"], "kind": tags[0], "turns": turns})
    return out


CONVERSATIONS = _conversations()


def _record(row: dict[str, Any]) -> None:
    with _lock, TURNS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


class Merchant(HttpUser):
    wait_time = constant(5)

    def on_start(self) -> None:
        i = next(_next_merchant) % len(MERCHANTS)
        self.merchant = MERCHANTS[i]
        self.token = TOKENS[i % len(TOKENS)] if TOKENS else ""

    @task
    def conversation(self) -> None:
        case = random.choice(CONVERSATIONS)
        session = f"load-{uuid.uuid4().hex[:8]}"
        for n, message in enumerate(case["turns"]):
            self._turn(case, n, message, session)
            if n < len(case["turns"]) - 1:
                time.sleep(5)

    def _turn(self, case: dict[str, Any], n: int, message: str, session: str) -> None:
        started = time.perf_counter()
        first_ms: float | None = None
        work_ms: float | None = None
        final: dict[str, Any] | None = None
        error = None
        status = 0
        try:
            with self.client.post(
                "/chat/stream",
                json={"message": message, "user_id": self.merchant, "session_id": session},
                headers={"Authorization": f"Bearer {self.token}"},
                stream=True,
                catch_response=True,
                name="/chat/stream",
                timeout=180,
            ) as response:
                status = response.status_code
                if status != 200:
                    # status 0: the request never got a response (connection error)
                    detail = f": {response.error!r}"[:160] if status == 0 else ""
                    error = f"http {status}{detail}"
                    response.failure(error)
                else:
                    kind = None
                    for raw in response.iter_lines(decode_unicode=True):
                        if not raw:
                            continue
                        if raw.startswith("event:"):
                            kind = raw.split(":", 1)[1].strip()
                            if first_ms is None:
                                first_ms = (time.perf_counter() - started) * 1000
                        elif raw.startswith("data:") and kind == "status" and work_ms is None:
                            step = json.loads(raw.split(":", 1)[1]).get("step")
                            if step in WORK_STEPS:
                                work_ms = (time.perf_counter() - started) * 1000
                        elif raw.startswith("data:") and kind in ("final", "error"):
                            data = json.loads(raw.split(":", 1)[1])
                            if kind == "final":
                                final = data
                            else:
                                error = str(data.get("code"))
                    if final is None:
                        error = error or "no final event"
                        response.failure(error)
                    else:
                        response.success()
        except Exception as exc:  # network errors count as failed turns
            error = type(exc).__name__
        total_ms = (time.perf_counter() - started) * 1000
        if first_ms is not None:
            events.request.fire(
                request_type="SSE",
                name="first_event",
                response_time=first_ms,
                response_length=0,
                exception=None,
            )
        _record(
            {
                "case": case["id"],
                "kind": case["kind"],
                "turn": n,
                "merchant": self.merchant,
                "http_status": status,
                "error": error,
                "first_event_ms": round(first_ms) if first_ms is not None else None,
                "first_work_ms": round(work_ms) if work_ms is not None else None,
                "total_ms": round(total_ms),
                "outcome": (final or {}).get("outcome"),
                "cost_usd": ((final or {}).get("usage") or {}).get("cost_usd"),
                "at": time.time(),
            }
        )
