"""Sliding-window limiter: limits apply and memory stays bounded."""

from blackkite.auth.ratelimit import SlidingWindowLimiter


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_limit_and_window():
    clock = Clock()
    lim = SlidingWindowLimiter(2, window=60, clock=clock)
    lim.hit("a")
    lim.hit("a")
    assert not lim.would_allow("a")
    clock.t += 61
    assert lim.would_allow("a")


def test_lookup_of_unknown_key_stores_nothing():
    lim = SlidingWindowLimiter(2, window=60, clock=Clock())
    for i in range(1000):
        assert lim.would_allow(f"ip-{i}")
    assert len(lim) == 0


def test_expired_key_dropped_when_seen_again():
    clock = Clock()
    lim = SlidingWindowLimiter(2, window=60, clock=clock)
    lim.hit("a")
    clock.t += 61
    assert lim.would_allow("a")
    assert len(lim) == 0


def test_keys_never_seen_again_are_swept():
    clock = Clock()
    lim = SlidingWindowLimiter(5, window=60, clock=clock)
    for i in range(1000):
        lim.hit(f"ip-{i}")
    assert len(lim) == 1000
    clock.t += 61
    lim.hit("fresh")
    assert len(lim) == 1


def test_memory_bounded_under_churn():
    """Many distinct keys over many windows: held keys never exceed one window's worth."""
    clock = Clock()
    lim = SlidingWindowLimiter(5, window=60, clock=clock)
    peak = 0
    for i in range(20_000):
        clock.t += 0.1  # 600 new keys per window
        lim.hit(f"ip-{i}")
        peak = max(peak, len(lim))
    # At most two windows' worth between sweeps.
    assert peak <= 1201


def test_recent_keys_survive_sweep():
    clock = Clock()
    lim = SlidingWindowLimiter(1, window=60, clock=clock)
    lim.hit("old")
    clock.t += 50
    lim.hit("recent")
    clock.t += 20  # sweep due; "old" expired, "recent" is 20 s old
    lim.would_allow("x")
    assert len(lim) == 1
    assert not lim.would_allow("recent")
