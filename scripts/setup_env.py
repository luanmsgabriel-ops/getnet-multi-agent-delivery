"""Create .env from .env.example with a random JWT_SECRET. Never overwrites an existing .env."""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    env = ROOT / ".env"
    if env.exists():
        print(".env already exists; leaving it untouched.")
        return 0
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    content = template.replace("JWT_SECRET=", f"JWT_SECRET={secrets.token_urlsafe(48)}", 1)
    content = content.replace("WEBHOOK_SECRET=", f"WEBHOOK_SECRET={secrets.token_urlsafe(32)}", 1)
    env.write_text(content, encoding="utf-8")
    print("Created .env. Add your ANTHROPIC_API_KEY to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
