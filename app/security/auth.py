"""JWT authentication and scope-based authorization.

Two token sources (docs/adr/015):
- OIDC (`OIDC_ISSUER` set, the compose default): RS256/ES256 tokens from an external issuer,
  checked against the keys it publishes (JWKS). Local tokens are refused in this mode.
- Local HS256 tokens signed with `JWT_SECRET`, for the offline tests and a quick local run.

The effective identity is the token subject (`sub`). The `user_id` in a request body is
only accepted when it matches the subject; it is never trusted on its own.
"""

import logging
import math
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import httpx2 as httpx
import jwt

from app.config import Settings

log = logging.getLogger("getnet.auth")

MERCHANT_SCOPES = (
    "chat:use",
    "sales:read",
    "receivables:read",
    "terminal:read",
    "tickets:read",
    "tickets:write",
    "actions:write",  # confirm two-phase actions (anticipation, terminal service)
)
OPERATOR_SCOPES = ("operator",)
KNOWN_SCOPES = frozenset(MERCHANT_SCOPES + OPERATOR_SCOPES)


# Asymmetric algorithms only: `none` and HS256 (which a public key could forge) are refused.
OIDC_ALGORITHMS = ("RS256", "ES256")
JWKS_TTL_SECONDS = 300.0  # re-read the key set at most every 5 minutes...
JWKS_REFRESH_COOLDOWN_SECONDS = 30.0  # ...or sooner on an unknown key id, at most every 30 s
CLOCK_SKEW_SECONDS = 30
REQUIRED_CLAIMS = ["sub", "exp", "jti", "iss", "aud"]

Fetch = Callable[[str], dict[str, Any]]


class AuthError(Exception):
    """Raised for authentication (401) and authorization (403) failures."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Principal:
    sub: str
    tenant: str
    scopes: frozenset[str]
    jti: str

    def has(self, scope: str) -> bool:
        return scope in self.scopes


def require_scope(principal: Principal, scope: str) -> None:
    if not principal.has(scope):
        raise AuthError(403, "insufficient_scope", f"Token lacks the '{scope}' scope.")


def _fetch_json(url: str) -> dict[str, Any]:
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return data


class OidcVerifier:
    """Checks tokens from an external OIDC issuer against the keys it publishes (JWKS).

    The key set comes from the issuer's discovery document and is cached. A token signed
    with a key id not in the cache triggers one refresh (key rotation), throttled so that
    tokens with made-up key ids cannot flood the issuer. If the issuer is down, the cached
    keys keep working.
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_url: str | None = None,
        fetch: Fetch | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self._jwks_url = jwks_url
        self._fetch = fetch or _fetch_json
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = -math.inf
        self._lock = threading.Lock()

    def _discover(self) -> str:
        if self._jwks_url is None:
            doc = self._fetch(f"{self.issuer}/.well-known/openid-configuration")
            if str(doc.get("issuer", "")).rstrip("/") != self.issuer:
                raise ValueError("discovery document is for another issuer")
            self._jwks_url = str(doc["jwks_uri"])
        return self._jwks_url

    def _refresh(self) -> None:
        jwks = jwt.PyJWKSet.from_dict(self._fetch(self._discover()))
        self._keys = {
            k.key_id: k for k in jwks.keys if k.key_id and k.public_key_use in (None, "sig")
        }
        self._fetched_at = self._clock()

    def _key(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            age = self._clock() - self._fetched_at
            if age > JWKS_TTL_SECONDS or (
                kid not in self._keys and age > JWKS_REFRESH_COOLDOWN_SECONDS
            ):
                try:
                    self._refresh()
                except (httpx.HTTPError, ValueError, KeyError, jwt.PyJWTError) as exc:
                    if not self._keys:
                        raise AuthError(
                            503, "auth_unavailable", "Identity provider unavailable."
                        ) from exc
                    log.warning("jwks_refresh_failed", extra={"error": type(exc).__name__})
            key = self._keys.get(kid)
        if key is None:
            raise AuthError(401, "invalid_token", "Invalid token.")
        return key

    def ready(self) -> bool:
        try:
            with self._lock:
                if not self._keys:
                    self._refresh()
            return bool(self._keys)
        except (httpx.HTTPError, ValueError, KeyError, jwt.PyJWTError):
            return False

    def decode(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        alg, kid = header.get("alg"), header.get("kid")
        if alg not in OIDC_ALGORITHMS or not isinstance(kid, str):
            raise jwt.InvalidAlgorithmError("algorithm or key id not accepted")
        key = self._key(kid)
        if key.algorithm_name != alg:  # the token must use the algorithm of the key it names
            raise jwt.InvalidAlgorithmError("algorithm does not match the key")
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=[alg],
            audience=self.audience,
            issuer=self.issuer,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": REQUIRED_CLAIMS},
        )
        return claims


@lru_cache
def oidc_verifier(issuer: str, audience: str, jwks_url: str | None = None) -> OidcVerifier:
    """One verifier (and key cache) per issuer for the process."""
    return OidcVerifier(issuer, audience, jwks_url)


def verifier_for(settings: Settings) -> OidcVerifier | None:
    if not settings.oidc_issuer:
        return None
    return oidc_verifier(settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url)


def _scopes(claims: dict[str, Any]) -> frozenset[str]:
    raw = claims.get("scope", claims.get("scp", ""))
    names = raw.split() if isinstance(raw, str) else [str(x) for x in raw or []]
    # Identity providers add their own scopes (openid, profile...); keep only ours.
    return frozenset(names) & KNOWN_SCOPES


def issue_token(
    settings: Settings,
    sub: str,
    tenant: str = "demo",
    scopes: tuple[str, ...] = MERCHANT_SCOPES,
    ttl_seconds: int | None = None,
) -> tuple[str, str]:
    if settings.oidc_issuer or settings.jwt_secret is None:
        raise RuntimeError("Local tokens are disabled: tokens come from the OIDC issuer.")
    unknown = set(scopes) - KNOWN_SCOPES
    if unknown:
        raise ValueError(f"Unknown scopes: {sorted(unknown)}")
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    claims = {
        "sub": sub,
        "tenant": tenant,
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=ttl_seconds or settings.jwt_default_ttl_seconds),
        "jti": jti,
    }
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    return token, jti


def decode_token(settings: Settings, token: str, verifier: OidcVerifier | None = None) -> Principal:
    verifier = verifier or verifier_for(settings)
    try:
        if verifier is not None:
            claims = verifier.decode(token)
        elif settings.jwt_secret is not None:
            claims = jwt.decode(
                token,
                settings.jwt_secret.get_secret_value(),
                algorithms=["HS256"],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options={"require": REQUIRED_CLAIMS},
            )
        else:  # unreachable: Settings requires one of the two
            raise AuthError(503, "auth_unavailable", "No token issuer configured.")
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(401, "token_expired", "Token expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthError(401, "invalid_token", "Invalid token.") from exc
    return Principal(
        sub=str(claims["sub"]),
        tenant=str(claims.get("tenant", "demo")),
        scopes=_scopes(claims),
        jti=str(claims["jti"]),
    )
