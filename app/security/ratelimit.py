"""Rate limiting per subject and global: in-process token buckets, or Redis when configured.

The in-process limiter suits one replica; with REDIS_URL the counters are shared by all
replicas. Both expose check(subject) -> None (allowed) or seconds to wait.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Protocol

import redis

if TYPE_CHECKING:
    from app.config import Settings

log = logging.getLogger("getnet.ratelimit")


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


class RedisRateLimiter:
    """Fixed one-minute windows in Redis, shared by every API replica (docs/adr/014).

    If Redis is unreachable the request is checked by an in-process limiter instead: limits stay
    enforced per replica rather than disappearing.
    """

    def __init__(
        self,
        client: "redis.Redis",
        per_subject_per_minute: int,
        global_per_minute: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.client = client
        self.per_subject, self.global_limit, self.clock = (
            per_subject_per_minute,
            global_per_minute,
            clock,
        )
        self.fallback = RateLimiter(per_subject_per_minute, global_per_minute)

    def check(self, subject: str) -> float | None:
        now = self.clock()
        window = int(now // 60)
        retry = 60 - (now % 60)
        g_key, s_key = f"rl:g:{window}", f"rl:s:{subject}:{window}"
        try:
            pipe = self.client.pipeline()
            pipe.incr(g_key)
            pipe.expire(g_key, 70)
            pipe.incr(s_key)
            pipe.expire(s_key, 70)
            g_count, _, s_count, _ = pipe.execute()
        except redis.RedisError:
            log.warning("redis unavailable; using the in-process rate limiter")
            return self.fallback.check(subject)
        if int(g_count) > self.global_limit or int(s_count) > self.per_subject:
            return retry
        return None


class Limiter(Protocol):
    def check(self, subject: str) -> float | None: ...


def make_limiter(settings: "Settings") -> Limiter:
    if settings.redis_url:
        return RedisRateLimiter(
            redis.Redis.from_url(settings.redis_url, socket_timeout=0.5),
            settings.rate_limit_per_minute,
            settings.rate_limit_global_per_minute,
        )
    return RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_global_per_minute)
