"""Rate limit for magic-link requests.

In-process sliding window: for each key (an email address or a client IP) we keep
the timestamps of accepted requests in the last `window` seconds and refuse a new
one once `limit` is reached. State lives in memory, so it is per API process and
resets on restart. That fits the single-VPS, single-process deployment; with more
than one API worker this must move to the database or a shared store.

The limit is applied before we look the email up, so a limited response says
nothing about whether an account exists.
"""

import hashlib
import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    """Memory is bounded by the keys seen in the last window: a key whose hits have
    all expired is dropped when it is next looked at, and a full sweep at most once
    per window drops keys that are never looked at again."""

    def __init__(
        self,
        limit: int,
        window: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = clock()

    def _expire(self, hits: deque[float], now: float) -> None:
        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        cutoff = now - self.window
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[key]

    def _count(self, key: str, now: float) -> int:
        self._sweep(now)
        hits = self._hits.get(key)
        if hits is None:
            return 0
        self._expire(hits, now)
        if not hits:
            del self._hits[key]
            return 0
        return len(hits)

    def would_allow(self, key: str) -> bool:
        with self._lock:
            return self._count(key, self.clock()) < self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._count(key, now)
            self._hits.setdefault(key, deque()).append(now)

    def __len__(self) -> int:
        """Number of keys currently held (for tests and monitoring)."""
        with self._lock:
            return len(self._hits)


class UnsubscribeLimiter:
    """POST /api/unsubscribe: a per-address flood ceiling, checked first, and a
    per-token limit keyed by the token's hash (the raw token is not kept)."""

    def __init__(self, per_token: int, per_ip: int, window: float = 3600.0) -> None:
        self.token = SlidingWindowLimiter(per_token, window)
        self.ip = SlidingWindowLimiter(per_ip, window)

    def allow_ip(self, ip: str) -> bool:
        if not self.ip.would_allow(ip):
            return False
        self.ip.hit(ip)
        return True

    def allow_token(self, token: str) -> bool:
        key = hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()
        if not self.token.would_allow(key):
            return False
        self.token.hit(key)
        return True


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
