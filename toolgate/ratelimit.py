"""In-memory token-bucket rate limiting (thread-safe)."""
from __future__ import annotations

import threading
import time


class TokenBucket:
    """A classic token bucket refilled continuously at ``rate_per_second``."""

    def __init__(self, capacity: int, rate_per_second: float):
        self.capacity = float(capacity)
        self.rate = float(rate_per_second)
        self.tokens = float(capacity)
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def allow(self, tokens: float = 1.0) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def retry_after(self) -> float:
        if self.rate <= 0:
            return 60.0
        needed = 1.0 - self.tokens
        return max(0.0, needed / self.rate)


class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str, per_minute: int) -> tuple[bool, float]:
        if per_minute <= 0:
            return True, 0.0
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(per_minute, per_minute / 60.0)
                self._buckets[key] = bucket
        allowed = bucket.allow()
        return allowed, (0.0 if allowed else bucket.retry_after())
