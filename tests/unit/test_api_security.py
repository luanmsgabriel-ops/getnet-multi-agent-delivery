"""Authentication, authorization, rate limiting and the /chat guard rails of the API."""

from collections.abc import Callable

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import SECRET, auth

CHAT = {"message": "Quando cai o dinheiro de ontem?", "user_id": "cliente1988"}


def test_health_is_public(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-request-id"]


def test_ready_reports_missing_llm(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"database": True, "llm": False}


def test_chat_requires_token(client: TestClient) -> None:
    r = client.post("/chat", json=CHAT)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "missing_token"
    assert r.headers["www-authenticate"] == "Bearer"


def test_rejects_token_signed_with_other_key(client: TestClient) -> None:
    forged = jwt.encode(
        {
            "sub": "cliente1988",
            "exp": 9999999999,
            "jti": "x",
            "iss": "getnet-agents",
            "aud": "getnet-chat",
        },
        "other" * 10,
        "HS256",
    )
    r = client.post("/chat", json=CHAT, headers=auth(forged))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_rejects_unsigned_token(client: TestClient) -> None:
    unsigned = jwt.encode(
        {
            "sub": "cliente1988",
            "exp": 9999999999,
            "jti": "x",
            "iss": "getnet-agents",
            "aud": "getnet-chat",
        },
        None,
        "none",
    )
    assert client.post("/chat", json=CHAT, headers=auth(unsigned)).status_code == 401


def test_rejects_expired_token(client: TestClient, token: Callable[..., str]) -> None:
    r = client.post("/chat", json=CHAT, headers=auth(token(ttl=-10)))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"


def test_rejects_revoked_token(client: TestClient, token: Callable[..., str]) -> None:
    tok = token()
    jti = jwt.decode(tok, SECRET, algorithms=["HS256"], audience="getnet-chat")["jti"]
    client.app.state.db.revoke(jti, "now")  # type: ignore[attr-defined]
    r = client.get("/me", headers=auth(tok))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_revoked"


def test_identity_comes_from_token_not_body(client: TestClient, token: Callable[..., str]) -> None:
    r = client.post("/chat", json={**CHAT, "user_id": "cliente2000"}, headers=auth(token()))
    assert r.status_code == 403 and r.json()["error"]["code"] == "user_mismatch"


def test_chat_requires_chat_scope(client: TestClient, token: Callable[..., str]) -> None:
    r = client.post("/chat", json=CHAT, headers=auth(token(scopes=("sales:read",))))
    assert r.status_code == 403 and r.json()["error"]["code"] == "insufficient_scope"


def test_chat_without_llm_key_is_explicit_503(
    client: TestClient, token: Callable[..., str]
) -> None:
    r = client.post("/chat", json=CHAT, headers=auth(token()))
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_not_configured"


def test_message_length_is_bounded(client: TestClient, token: Callable[..., str]) -> None:
    r = client.post("/chat", json={**CHAT, "message": "a" * 5000}, headers=auth(token()))
    assert r.status_code == 422 and r.json()["error"]["code"] == "message_too_long"


def test_validation_errors_use_error_envelope(
    client: TestClient, token: Callable[..., str]
) -> None:
    r = client.post("/chat", json={"user_id": "cliente1988"}, headers=auth(token()))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_rate_limit_returns_429_with_retry_after(
    settings: Settings, token: Callable[..., str]
) -> None:
    limited = settings.model_copy(update={"rate_limit_per_minute": 2})
    with TestClient(create_app(limited)) as c:
        codes = [c.post("/chat", json=CHAT, headers=auth(token())).status_code for _ in range(3)]
        r = c.post("/chat", json=CHAT, headers=auth(token()))
    assert codes[:2] == [503, 503]
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


@pytest.mark.parametrize("path", ["/me"])
def test_every_data_route_requires_auth(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


def test_all_non_public_routes_are_protected(client: TestClient) -> None:
    public = {
        "/health",
        "/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
    for route in client.app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", "")
        if path in public:
            continue
        for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
            r = client.request(method, path, json={})
            assert r.status_code == 401, f"{method} {path} is not protected"
