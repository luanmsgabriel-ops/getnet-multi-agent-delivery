"""Demo webhook receiver: verifies the HMAC signature and logs each notification.

Stands in for the operator's queue tool (Slack/Teams/helpdesk) and the merchant's app in
`docker compose`. Run: python -m app.hitl.sink  (port 9000)
"""

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.hitl.notify import sign


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        secret = os.environ.get("WEBHOOK_SECRET")
        expected = sign(secret, body, self.headers.get("X-Getnet-Timestamp", "")) if secret else ""
        valid = (not secret) or hmac.compare_digest(
            expected, self.headers.get("X-Getnet-Signature", "")
        )
        self.send_response(204 if valid else 401)
        self.end_headers()
        event = json.loads(body or b"{}")
        print(
            json.dumps(
                {
                    "target": self.path.strip("/"),
                    "signature_valid": valid,
                    "event": event.get("event"),
                    "data": event.get("data"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    def log_message(self, format: str, *args: object) -> None:  # quiet default access log
        return


def main() -> None:
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()  # noqa: S104  # nosec B104


if __name__ == "__main__":
    main()
