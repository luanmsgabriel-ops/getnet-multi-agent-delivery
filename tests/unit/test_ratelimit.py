from app.security.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_per_subject_bucket_refills_over_time() -> None:
    clock = FakeClock()
    rl = RateLimiter(per_subject_per_minute=2, global_per_minute=100, clock=clock)
    assert rl.check("a") is None and rl.check("a") is None
    wait = rl.check("a")
    assert wait is not None and 0 < wait <= 30
    assert rl.check("b") is None  # other subjects are independent
    clock.t += 30
    assert rl.check("a") is None


def test_global_bucket_limits_everyone() -> None:
    rl = RateLimiter(per_subject_per_minute=100, global_per_minute=2, clock=FakeClock())
    assert rl.check("a") is None and rl.check("b") is None
    assert rl.check("c") is not None
