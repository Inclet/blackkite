"""Rate limit for magic-link requests.

In-process sliding window: for each key (an email address or a client IP) we keep
the timestamps of accepted requests in the last `window` seconds and refuse a new
one once `limit` is reached. State lives in memory, so it is per API process and
resets on restart. That fits the single-VPS, single-process deployment; with more
than one API worker this must move to the database or a shared store.

The limit is applied before we look the email up, so a limited response says
nothing about whether an account exists.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(self, limit: int, window: float = 3600.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def would_allow(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, self.clock())) < self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._prune(key, now).append(now)


class LinkRequestLimiter:
    """Per-email and per-IP limits; a request must pass both."""

    def __init__(self, per_email: int, per_ip: int, window: float = 3600.0) -> None:
        self.email = SlidingWindowLimiter(per_email, window)
        self.ip = SlidingWindowLimiter(per_ip, window)

    def allow(self, email: str, ip: str) -> bool:
        if not (self.email.would_allow(email) and self.ip.would_allow(ip)):
            return False
        self.email.hit(email)
        self.ip.hit(ip)
        return True
