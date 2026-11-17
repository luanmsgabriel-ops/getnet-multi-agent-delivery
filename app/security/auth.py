"""JWT authentication and scope-based authorization.

The effective identity is the token subject (`sub`). The `user_id` in a request body is
only accepted when it matches the subject; it is never trusted on its own.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.config import Settings

MERCHANT_SCOPES = (
    "chat:use",
    "sales:read",
    "receivables:read",
    "terminal:read",
    "tickets:read",
    "tickets:write",
)
OPERATOR_SCOPES = ("operator",)
KNOWN_SCOPES = frozenset(MERCHANT_SCOPES + OPERATOR_SCOPES)


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


def issue_token(
    settings: Settings,
    sub: str,
    tenant: str = "demo",
    scopes: tuple[str, ...] = MERCHANT_SCOPES,
    ttl_seconds: int | None = None,
) -> tuple[str, str]:
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


def decode_token(settings: Settings, token: str) -> Principal:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "jti", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(401, "token_expired", "Token expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthError(401, "invalid_token", "Invalid token.") from exc
    return Principal(
        sub=str(claims["sub"]),
        tenant=str(claims.get("tenant", "demo")),
        scopes=frozenset(str(claims.get("scope", "")).split()),
        jti=str(claims["jti"]),
    )
