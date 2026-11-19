"""OIDC against a real provider (docs/adr/015). Runs when TEST_OIDC_ISSUER is set: the CI
service, or the compose provider (ops/oidc/config.json)."""

import os
import time
from collections.abc import Iterator
from pathlib import Path

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security.auth import OidcVerifier
from app.security.tokens import _oidc_token
from tests.fakes import ScriptedLLM

ISSUER = os.environ.get("TEST_OIDC_ISSUER")
pytestmark = pytest.mark.skipif(not ISSUER, reason="TEST_OIDC_ISSUER not set")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    assert ISSUER
    base = ISSUER.rsplit("/", 1)[0]
    for _ in range(60):  # the provider takes a few seconds to start
        try:
            if httpx.get(f"{base}/isalive", timeout=2.0).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return Settings(
        data_dir=tmp_path,
        oidc_issuer=ISSUER,
        anthropic_api_key=None,
        warm_knowledge_index=False,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    assert settings.oidc_issuer
    verifier = OidcVerifier(settings.oidc_issuer, settings.oidc_audience)
    llm = ScriptedLLM({})  # operator routes need the agents configured; no model call is made
    with TestClient(create_app(settings, llm=llm, verifier=verifier)) as c:
        yield c


def test_provider_tokens_work_end_to_end(settings: Settings, client: TestClient) -> None:
    tok = _oidc_token(settings, "cliente1988", ["chat:use", "sales:read"])
    r = client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "sub": "cliente1988",
        "tenant": "demo",
        "scopes": ["chat:use", "sales:read"],
    }
    assert client.get("/ready").json()["checks"]["identity_provider"] is True

    head, body, sig = tok.split(".")
    tampered = f"{head}.{body}.{sig[:-4]}AAAA"
    r = client.get("/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


def test_operator_scope_is_enforced(settings: Settings, client: TestClient) -> None:
    merchant = _oidc_token(settings, "cliente1988", ["chat:use"])
    r = client.get("/operator/handoffs", headers={"Authorization": f"Bearer {merchant}"})
    assert r.status_code == 403
    operator = _oidc_token(settings, "operador1", ["operator"])
    r = client.get("/operator/handoffs", headers={"Authorization": f"Bearer {operator}"})
    assert r.status_code == 200, r.text
