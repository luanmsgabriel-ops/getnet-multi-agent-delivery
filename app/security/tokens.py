"""CLI to issue and revoke local API tokens.

python -m app.security.tokens issue --sub cliente1988
python -m app.security.tokens issue --sub ana --scopes operator --ttl 28800
python -m app.security.tokens revoke --token <jwt>
"""

import argparse
import sys
from datetime import UTC, datetime

from app.config import get_settings
from app.data.db import Database
from app.security.auth import MERCHANT_SCOPES, decode_token, issue_token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.security.tokens")
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue", help="Issue a token")
    issue.add_argument("--sub", required=True, help="Subject (merchant id or operator name)")
    issue.add_argument("--tenant", default="demo")
    issue.add_argument("--scopes", nargs="+", default=list(MERCHANT_SCOPES))
    issue.add_argument("--ttl", type=int, default=None, help="Lifetime in seconds")
    revoke = sub.add_parser("revoke", help="Revoke a token by its jti")
    revoke.add_argument("--token", required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.command == "issue":
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
