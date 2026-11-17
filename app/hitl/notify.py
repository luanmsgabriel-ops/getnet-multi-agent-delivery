"""Signed webhook notifications (operator queue and merchant updates). Best effort."""

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx2 as httpx

log = logging.getLogger("getnet.hitl")


def sign(secret: str, body: bytes, timestamp: str) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return mac.hexdigest()


def send(url: str | None, secret: str | None, event: str, payload: dict[str, Any]) -> bool:
    """POST {event, data} with X-Getnet-Timestamp / X-Getnet-Signature (HMAC-SHA256)."""
    if not url:
        return False
    body = json.dumps({"event": event, "data": payload}, ensure_ascii=False).encode()
    timestamp = str(int(time.time()))
    headers = {"Content-Type": "application/json", "X-Getnet-Timestamp": timestamp}
    if secret:
        headers["X-Getnet-Signature"] = sign(secret, body, timestamp)
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=3.0)
        ok = response.status_code < 300
    except httpx.HTTPError:
        ok = False
    log.info("webhook event=%s delivered=%s", event, ok)
    return ok
