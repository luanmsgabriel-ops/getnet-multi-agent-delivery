from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security.auth import MERCHANT_SCOPES, issue_token

SECRET = "test-secret-" + "x" * 40


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        jwt_secret=SECRET,  # type: ignore[arg-type]
        anthropic_api_key=None,
        rate_limit_per_minute=1000,
        rate_limit_global_per_minute=1000,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def token(settings: Settings) -> Callable[..., str]:
    def make(
        sub: str = "cliente1988", scopes: tuple[str, ...] = MERCHANT_SCOPES, ttl: int | None = None
    ) -> str:
        return issue_token(settings, sub, "demo", scopes, ttl)[0]

    return make


def auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}
