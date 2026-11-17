"""Resilient JSON GET for public APIs: timeout, bounded retry and a per-host circuit breaker."""

import time
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx

TIMEOUT_S = 5.0
RETRIES = 2
BREAKER_THRESHOLD = 3
BREAKER_OPEN_S = 60.0
USER_AGENT = "getnet-agents-demo/3.0"


class UpstreamError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _Breaker:
    def __init__(self) -> None:
        self.failures: dict[str, int] = {}
        self.open_until: dict[str, float] = {}
        self.lock = Lock()

    def check(self, host: str) -> None:
        with self.lock:
            if self.open_until.get(host, 0) > time.monotonic():
                raise UpstreamError("upstream_error", f"{host} temporarily unavailable")

    def result(self, host: str, ok: bool) -> None:
        with self.lock:
            if ok:
                self.failures[host] = 0
                return
            self.failures[host] = self.failures.get(host, 0) + 1
            if self.failures[host] >= BREAKER_THRESHOLD:
                self.open_until[host] = time.monotonic() + BREAKER_OPEN_S
                self.failures[host] = 0


breaker = _Breaker()
_transport: httpx.BaseTransport | None = None  # tests inject a MockTransport


def get_json(url: str, params: dict[str, Any]) -> Any:
    host = urlsplit(url).netloc
    breaker.check(host)
    last: UpstreamError | None = None
    for attempt in range(RETRIES + 1):
        try:
            with httpx.Client(
                timeout=TIMEOUT_S, transport=_transport, headers={"User-Agent": USER_AGENT}
            ) as client:
                response = client.get(url, params=params)
            if response.status_code >= 500:
                last = UpstreamError("upstream_error", f"{host} returned {response.status_code}")
            elif response.status_code == 429:
                last = UpstreamError("rate_limited", f"{host} rate limited")
            elif response.status_code >= 400:
                breaker.result(host, True)
                raise UpstreamError("invalid_argument", f"{host} returned {response.status_code}")
            else:
                breaker.result(host, True)
                return response.json()
        except httpx.TimeoutException:
            last = UpstreamError("upstream_timeout", f"{host} timed out")
        except httpx.TransportError:
            last = UpstreamError("upstream_error", f"{host} unreachable")
        if attempt < RETRIES:
            time.sleep(0.3 * 2**attempt)
    breaker.result(host, False)
    assert last is not None
    raise last
