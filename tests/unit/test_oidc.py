"""OIDC token validation against a JWKS (R05.1): issuer, audience, key rotation, algorithms."""

import hashlib
import hmac
import json
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2 as httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security.auth import (
    JWKS_REFRESH_COOLDOWN_SECONDS,
    AuthError,
    OidcVerifier,
    decode_token,
    issue_token,
)

ISSUER = "http://idp.test/getnet"
AUDIENCE = "getnet-chat"
JWKS_URL = f"{ISSUER}/jwks"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Provider:
    """A fake identity provider: discovery document, a key set that can rotate, a fetch log."""

    def __init__(self) -> None:
        self.keys: dict[str, Any] = {}
        self.published: list[str] = []
        self.fetches: list[str] = []
        self.down = False
        self.rotate("k1")

    def rotate(self, kid: str, keep_old: bool = False) -> None:
        self.keys[kid] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.published = [*self.published, kid] if keep_old else [kid]

    def fetch(self, url: str) -> dict[str, Any]:
        self.fetches.append(url)
        if self.down:
            raise httpx.ConnectError("provider down")
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": ISSUER, "jwks_uri": JWKS_URL}
        assert url == JWKS_URL
        jwks = []
        for kid in self.published:
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.keys[kid].public_key()))
            jwks.append({**jwk, "kid": kid, "use": "sig", "alg": "RS256"})
        return {"keys": jwks}

    def token(self, kid: str = "k1", **overrides: Any) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": "cliente1988",
            "scope": "openid chat:use sales:read",
            "tenant": "demo",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=10),
            "jti": uuid.uuid4().hex,
            **overrides,
        }
        return jwt.encode(claims, self.keys[kid], algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def idp() -> Provider:
    return Provider()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def verifier(idp: Provider, clock: Clock) -> OidcVerifier:
    return OidcVerifier(ISSUER, AUDIENCE, fetch=idp.fetch, clock=clock)


@pytest.fixture
def oidc_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        oidc_issuer=ISSUER,
        jwt_secret=None,
        anthropic_api_key=None,
        warm_knowledge_index=False,
        _env_file=None,  # type: ignore[call-arg]
    )


def rejected(fn: Callable[[], object], code: str = "invalid_token", status: int = 401) -> None:
    with pytest.raises(AuthError) as err:
        fn()
    assert (err.value.status, err.value.code) == (status, code)


def test_valid_token_keeps_only_known_scopes(
    oidc_settings: Settings, idp: Provider, verifier: OidcVerifier
) -> None:
    p = decode_token(oidc_settings, idp.token(), verifier)
    assert p.sub == "cliente1988"
    assert p.scopes == {"chat:use", "sales:read"}  # "openid" dropped


def test_wrong_issuer_audience_and_expiry_are_rejected(
    oidc_settings: Settings, idp: Provider, verifier: OidcVerifier
) -> None:
    rejected(lambda: decode_token(oidc_settings, idp.token(iss="http://evil.test"), verifier))
    rejected(lambda: decode_token(oidc_settings, idp.token(aud="other-api"), verifier))
    past = datetime.now(UTC) - timedelta(hours=1)
    rejected(
        lambda: decode_token(oidc_settings, idp.token(exp=past), verifier), code="token_expired"
    )


def test_missing_jti_is_rejected(
    oidc_settings: Settings, idp: Provider, verifier: OidcVerifier
) -> None:
    now = datetime.now(UTC)
    claims = {"sub": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": now + timedelta(minutes=5)}
    tok = jwt.encode(claims, idp.keys["k1"], algorithm="RS256", headers={"kid": "k1"})
    rejected(lambda: decode_token(oidc_settings, tok, verifier))


def test_alg_none_and_hs256_with_the_public_key_are_rejected(
    oidc_settings: Settings, idp: Provider, verifier: OidcVerifier
) -> None:
    claims = jwt.decode(idp.token(), options={"verify_signature": False})
    unsigned = jwt.encode(claims, None, algorithm="none", headers={"kid": "k1"})
    rejected(lambda: decode_token(oidc_settings, unsigned, verifier))
    # Algorithm confusion: sign HS256 using the published public key as the HMAC secret.
    pem = (
        idp.keys["k1"]
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    header = json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode()
    body = json.dumps(claims, default=str).encode()
    signing = jwt.utils.base64url_encode(header) + b"." + jwt.utils.base64url_encode(body)

    sig = jwt.utils.base64url_encode(hmac.new(pem, signing, hashlib.sha256).digest())
    forged = (signing + b"." + sig).decode()
    rejected(lambda: decode_token(oidc_settings, forged, verifier))


def test_token_signed_by_another_key_with_a_known_kid_is_rejected(
    oidc_settings: Settings, idp: Provider, verifier: OidcVerifier
) -> None:
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(idp.token(), options={"verify_signature": False})
    forged = jwt.encode(claims, attacker, algorithm="RS256", headers={"kid": "k1"})
    rejected(lambda: decode_token(oidc_settings, forged, verifier))
    ec_key = ec.generate_private_key(ec.SECP256R1())
    forged_ec = jwt.encode(claims, ec_key, algorithm="ES256", headers={"kid": "k1"})
    rejected(lambda: decode_token(oidc_settings, forged_ec, verifier))


def test_key_rotation_refreshes_once_and_drops_the_old_key(
    oidc_settings: Settings, idp: Provider, verifier: OidcVerifier, clock: Clock
) -> None:
    old = idp.token("k1")
    decode_token(oidc_settings, old, verifier)
    assert idp.fetches.count(JWKS_URL) == 1
    clock.now += JWKS_REFRESH_COOLDOWN_SECONDS + 1
    idp.rotate("k2")  # the provider retires k1
    assert decode_token(oidc_settings, idp.token("k2"), verifier).sub == "cliente1988"
    assert idp.fetches.count(JWKS_URL) == 2
    rejected(lambda: decode_token(oidc_settings, old, verifier))


def test_unknown_key_ids_cannot_flood_the_provider(
    oidc_settings: Settings, idp: Provider, verifier: OidcVerifier
) -> None:
    decode_token(oidc_settings, idp.token(), verifier)
    idp.rotate("k9", keep_old=True)
    for _ in range(20):
        rejected(lambda: decode_token(oidc_settings, idp.token("k9"), verifier))
    assert idp.fetches.count(JWKS_URL) == 1  # still inside the cooldown


def test_provider_down_uses_cached_keys_or_returns_503(
    oidc_settings: Settings, idp: Provider, clock: Clock
) -> None:
    cold = OidcVerifier(ISSUER, AUDIENCE, fetch=idp.fetch, clock=clock)
    idp.down = True
    rejected(lambda: decode_token(oidc_settings, idp.token(), cold), "auth_unavailable", 503)
    assert cold.ready() is False
    idp.down = False
    warm = OidcVerifier(ISSUER, AUDIENCE, fetch=idp.fetch, clock=clock)
    decode_token(oidc_settings, idp.token(), warm)
    idp.down = True
    clock.now += 3600  # cache is stale and the refresh fails: keep the keys we have
    assert decode_token(oidc_settings, idp.token(), warm).sub == "cliente1988"


def test_discovery_for_another_issuer_is_refused(clock: Clock) -> None:
    def fetch(url: str) -> dict[str, Any]:
        return {"issuer": "http://evil.test", "jwks_uri": "http://evil.test/jwks"}

    v = OidcVerifier(ISSUER, AUDIENCE, fetch=fetch, clock=clock)
    assert v.ready() is False


def test_local_tokens_are_disabled_under_oidc(oidc_settings: Settings) -> None:
    with pytest.raises(RuntimeError):
        issue_token(oidc_settings, "cliente1988")


def test_settings_need_a_token_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="OIDC_ISSUER"):
        Settings(data_dir=tmp_path, jwt_secret=None, _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def oidc_client(oidc_settings: Settings, verifier: OidcVerifier) -> Iterator[TestClient]:
    with TestClient(create_app(oidc_settings, verifier=verifier)) as c:
        yield c


def test_api_accepts_oidc_tokens_and_refuses_local_ones(
    oidc_client: TestClient, idp: Provider
) -> None:
    r = oidc_client.get("/me", headers={"Authorization": f"Bearer {idp.token()}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "cliente1988"
    local = Settings(
        data_dir=Path("."),
        jwt_secret="y" * 40,  # type: ignore[arg-type]
        _env_file=None,  # type: ignore[call-arg]
    )
    hs = issue_token(local, "cliente1988")[0]
    r = oidc_client.get("/me", headers={"Authorization": f"Bearer {hs}"})
    assert r.status_code == 401
    ready = oidc_client.get("/ready").json()
    assert ready["checks"]["identity_provider"] is True
