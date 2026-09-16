"""Client-side rate limiting.

Best practice #1 for this assignment.

Two separate guarantees:

1. `min_interval` - never send two requests closer together than N seconds.
   arXiv asks callers to leave about three seconds between requests, and
   ignoring that is what earns an HTTP 429 response.
2. `max_calls` per `period` - a hard ceiling on how many requests a single
   server process can make in a rolling time window. An LLM client can call a
   tool in a loop, so the ceiling protects the upstream service (and the user's
   quota) even when the caller misbehaves.

Sliding-window counter approach described in the Cloudflare write-up on rate
limiting techniques:
https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
"""

import threading
import time
from collections import deque


class RateLimitExceeded(Exception):
    """Raised when a caller exceeds the ceiling for the current time window."""


class RateLimiter:
    """Allow at most `max_calls` per `period` seconds, spaced `min_interval` apart.

    Thread-safe: the MCP SDK runs synchronous tool functions in a worker thread
    pool, so two calls really can land at the same moment.
    """

    def __init__(self, max_calls: int, period: float, min_interval: float = 0.0):
        self.max_calls = max_calls
        self.period = period
        self.min_interval = min_interval
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Record one call, sleeping if needed. Raises RateLimitExceeded if over budget."""
        with self._lock:
            now = time.monotonic()

            # Drop timestamps that have aged out of the window.
            while self._calls and now - self._calls[0] > self.period:
                self._calls.popleft()

            if len(self._calls) >= self.max_calls:
                retry_in = self.period - (now - self._calls[0])
                raise RateLimitExceeded(
                    f"Rate limit reached: {self.max_calls} requests per "
                    f"{self.period:.0f}s. Try again in {retry_in:.0f}s."
                )

            # Space this call out from the previous one.
            if self._calls and self.min_interval > 0:
                gap = now - self._calls[-1]
                if gap < self.min_interval:
                    time.sleep(self.min_interval - gap)
                    now = time.monotonic()

            self._calls.append(now)

    def reset(self) -> None:
        """Clear the window. Used by tests, never during normal operation."""
        with self._lock:
            self._calls.clear()
