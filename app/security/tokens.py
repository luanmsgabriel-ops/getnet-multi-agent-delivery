"""CLI to issue and revoke API tokens.

python -m app.security.tokens issue --sub cliente1988
python -m app.security.tokens issue --sub ana --scopes operator --ttl 28800
python -m app.security.tokens revoke --token <jwt>

With `OIDC_ISSUER` set (the compose default), `issue` asks the issuer for a token with the
client-credentials grant, using the subject as client id. That only works against the
development provider in docker-compose.yml, which accepts any client; a real identity
provider issues tokens through its own login flow. Without it, `issue` signs a local token.
"""

import argparse
import sys
from datetime import UTC, datetime

import httpx2 as httpx

from app.config import Settings, get_settings
from app.data.db import Database
from app.security.auth import MERCHANT_SCOPES, decode_token, issue_token

DEV_CLIENT_SECRET = "dev"  # noqa: S105 - not a secret: the development provider ignores it


def _oidc_token(settings: Settings, sub: str, scopes: list[str]) -> str:
    issuer = str(settings.oidc_issuer).rstrip("/")
    doc = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10.0).json()
    response = httpx.post(
        str(doc["token_endpoint"]),
        data={
            "grant_type": "client_credentials",
            "client_id": sub,
            "client_secret": DEV_CLIENT_SECRET,
            "scope": " ".join(scopes),
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.security.tokens")
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue", help="Issue a token")
    issue.add_argument("--sub", required=True, help="Subject (merchant id or operator name)")
    issue.add_argument("--tenant", default="demo")
    issue.add_argument("--scopes", nargs="+", default=list(MERCHANT_SCOPES))
    issue.add_argument("--ttl", type=int, default=None, help="Lifetime in seconds (local only)")
    revoke = sub.add_parser("revoke", help="Revoke a token by its jti")
    revoke.add_argument("--token", required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.command == "issue":
        if settings.oidc_issuer:
            token = _oidc_token(settings, args.sub, args.scopes)
        else:
            token, _ = issue_token(settings, args.sub, args.tenant, tuple(args.scopes), args.ttl)
        sys.stdout.write(token + "\n")
        return 0
    principal = decode_token(settings, args.token)
    db = Database(settings.state_database_url or settings.db_path)
    db.init_state()
    db.revoke(principal.jti, datetime.now(UTC).isoformat())
    sys.stdout.write(f"revoked jti={principal.jti}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
