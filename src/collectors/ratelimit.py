"""Minimum-interval rate limiter (politeness). Clock and sleeper are injectable for tests."""
from __future__ import annotations

import time
from typing import Callable


class RateLimiter:
    def __init__(
        self,
        requests_per_second: float,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.min_interval = 1.0 / requests_per_second
        self._sleep = sleeper
        self._clock = clock
        self._last: float | None = None
        self.total_wait = 0.0

    def wait(self) -> float:
        """Block until the next request is allowed; return the seconds waited."""
        now = self._clock()
        waited = 0.0
        if self._last is not None:
            remaining = self.min_interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
                waited = remaining
                now = self._clock()
        self._last = now
        self.total_wait += waited
        return waited


class NullRateLimiter:
    """Used for the mock adapter: no network, so nothing to be polite to."""

    total_wait = 0.0

    def wait(self) -> float:
        return 0.0
