"""App state in Postgres and rate limits in Redis (docs/adr/014).

The live tests run when TEST_POSTGRES_URL / TEST_REDIS_URL are set (CI services, or the compose
stack); each test gets its own Postgres schema. The unit tests always run.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import quote

import fakeredis
import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from app.config import Settings
from app.data.db import Database, to_postgres
from app.main import create_app
from app.security.ratelimit import RedisRateLimiter
from tests.conftest import auth
from tests.fakes import ScriptedLLM, calls, text

PG = os.environ.get("TEST_POSTGRES_URL")
REDIS = os.environ.get("TEST_REDIS_URL")


# ---------------------------------------------------------------- unit (always run)
def test_sql_dialect_translation() -> None:
    assert to_postgres("SELECT 1 FROM t WHERE a = ? AND b = ?") == (
        "SELECT 1 FROM t WHERE a = %s AND b = %s"
    )
    assert to_postgres("INSERT OR IGNORE INTO r(j) VALUES (?)") == (
        "INSERT INTO r(j) VALUES (%s) ON CONFLICT DO NOTHING"
    )
    assert "BIGSERIAL PRIMARY KEY" in to_postgres("id INTEGER PRIMARY KEY AUTOINCREMENT")


def test_redis_limiter_shares_counts_across_replicas() -> None:
    server = fakeredis.FakeServer()
    clock = lambda: 1_000.0  # noqa: E731
    a = RedisRateLimiter(fakeredis.FakeRedis(server=server), 2, 100, clock)
    b = RedisRateLimiter(fakeredis.FakeRedis(server=server), 2, 100, clock)
    assert a.check("m1") is None and b.check("m1") is None
    wait = a.check("m1")  # third request in the same minute, counted across both replicas
    assert wait is not None and 0 < wait <= 60
    assert b.check("m2") is None  # other merchant unaffected


def test_redis_outage_falls_back_to_local_limits() -> None:
    class Down:
        def pipeline(self) -> Any:
            raise redis.ConnectionError("down")

    limiter = RedisRateLimiter(Down(), 1, 100)  # type: ignore[arg-type]
    assert limiter.check("m1") is None
    assert limiter.check("m1") is not None  # still limited, by the in-process fallback


# ---------------------------------------------------------------- live Postgres / Redis
@pytest.fixture
def pg_url() -> Iterator[str]:
    if not PG:
        pytest.skip("TEST_POSTGRES_URL not set")
    schema = f"t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(PG, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    sep = "&" if "?" in PG else "?"
    yield f"{PG}{sep}options={quote(f'-csearch_path={schema}')}"
    with psycopg.connect(PG, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.fixture
def notify(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []
    monkeypatch.setattr(
        "app.hitl.notify.send", lambda url, secret, event, payload: sent.append(event)
    )
    return sent


def _chat(c: TestClient, tok: str, message: str, session: str = "s1") -> dict[str, Any]:
    r = c.post(
        "/chat",
        headers=auth(tok),
        json={"message": message, "user_id": "cliente1988", "session_id": session},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_state_lives_in_postgres_across_restarts(
    settings: Settings, pg_url: str, token: Callable[..., str], notify: list[str]
) -> None:
    pg_settings = settings.model_copy(update={"state_database_url": pg_url})
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(
                    ("remember", {"category": "business_profile", "value": "padaria com 2 lojas"}),
                    (
                        "escalate_to_human",
                        {
                            "reason": "charge_dispute",
                            "priority": "high",
                            "summary": "venda duplicada",
                        },
                    ),
                ),
                text("O especialista respondeu: estorno em análise."),
            ]
        }
    )
    merchant, operator = token(), token(sub="operador1", scopes=("operator",))
    with TestClient(create_app(pg_settings, llm=llm)) as c:
        first = _chat(c, merchant, "Tenho uma padaria. Cobraram duas vezes meu cliente!")
        handoff_id = first["handoff"]["id"]
    # a new app instance (another replica, or a restart) sees the same state
    with TestClient(create_app(pg_settings, llm=llm)) as c:
        queue = c.get("/operator/handoffs", headers=auth(operator)).json()
        assert [h["id"] for h in queue] == [handoff_id]
        reply = c.post(
            f"/operator/handoffs/{handoff_id}/reply",
            headers=auth(operator),
            json={"action": "reply", "message": "Estorno em análise."},
        )
        assert reply.status_code == 200 and reply.json()["outcome"] == "handoff_resolved"
        events = c.get("/sessions/s1/events?wait_s=1", headers=auth(merchant)).text
        assert "handoff.resolved" in events
        assert "padaria" in c.get("/me/memory", headers=auth(merchant)).json()["business_profile"]
    with psycopg.connect(pg_url) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()"
            )
        }
    assert {"handoffs", "session_events", "merchant_memory", "checkpoints"} <= tables
    assert notify[:1] == ["handoff.created"]


def test_revocation_is_shared_through_postgres(
    settings: Settings, pg_url: str, token: Callable[..., str]
) -> None:
    from app.security.auth import decode_token

    pg_settings = settings.model_copy(update={"state_database_url": pg_url})
    tok = token()
    with TestClient(create_app(pg_settings, llm=ScriptedLLM({}))) as c:
        assert c.get("/me", headers=auth(tok)).status_code == 200
        state = Database(pg_url)
        state.revoke(decode_token(pg_settings, tok).jti, "2026-11-19T00:00:00Z")
        assert c.get("/me", headers=auth(tok)).status_code == 401


def test_rate_limit_is_shared_by_two_replicas_through_redis(
    settings: Settings, token: Callable[..., str]
) -> None:
    if not REDIS:
        pytest.skip("TEST_REDIS_URL not set")
    redis.Redis.from_url(REDIS).flushdb()
    limited = settings.model_copy(update={"redis_url": REDIS, "rate_limit_per_minute": 2})
    llm = ScriptedLLM({"supervisor": [text("ok")]}, repeat_last=True)
    tok = token()
    with (
        TestClient(create_app(limited, llm=llm)) as a,
        TestClient(create_app(limited, llm=llm)) as b,
    ):
        codes = [
            a.post(
                "/chat", headers=auth(tok), json={"message": "oi", "user_id": "cliente1988"}
            ).status_code,
            b.post(
                "/chat", headers=auth(tok), json={"message": "oi", "user_id": "cliente1988"}
            ).status_code,
            a.post(
                "/chat", headers=auth(tok), json={"message": "oi", "user_id": "cliente1988"}
            ).status_code,
        ]
    assert codes == [200, 200, 429]
