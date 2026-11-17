"""In-process token-bucket rate limiting, per subject and global.

Single-process by design (one uvicorn worker). A multi-replica deployment would move
the buckets to Redis; the interface stays the same.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _Bucket:
    capacity: float
    refill_per_second: float
    tokens: float
    updated: float

    def take(self, now: float) -> float | None:
        """Consume one token; return None if allowed or seconds to wait if not."""
        self.tokens = min(
            self.capacity, self.tokens + (now - self.updated) * self.refill_per_second
        )
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return None
        return (1 - self.tokens) / self.refill_per_second


@dataclass
class RateLimiter:
    per_subject_per_minute: int
    global_per_minute: int
    clock: Callable[[], float] = time.monotonic
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def _bucket(self, key: str, per_minute: int, now: float) -> _Bucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(per_minute, per_minute / 60, per_minute, now)
            self._buckets[key] = bucket
        return bucket

    def check(self, subject: str) -> float | None:
        """Return None when allowed, otherwise the Retry-After in seconds."""
        with self._lock:
            now = self.clock()
            wait = self._bucket("__global__", self.global_per_minute, now).take(now)
            if wait is not None:
                return wait
            return self._bucket(subject, self.per_subject_per_minute, now).take(now)
