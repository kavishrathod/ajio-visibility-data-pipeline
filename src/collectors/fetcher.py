"""Central retry/backoff policy for timeouts and HTTP 429 responses."""
from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from .base import Adapter, RawResponse


class FetchExhausted(RuntimeError):
    def __init__(self, message: str, retry_count: int = 0) -> None:
        super().__init__(message)
        self.retry_count = retry_count


def retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            current = now or datetime.now(timezone.utc)
            return max(0.0, (parsed.astimezone(timezone.utc) - current).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def backoff_delay(attempt: int, base: float, cap: float, jitter_fraction: float, rng: random.Random) -> float:
    """Exponential backoff with bounded jitter.

    The deterministic part is ``min(cap, base * 2**attempt)``. With
    ``jitter_fraction=0.5`` the actual delay is uniform in [50%, 100%] of that,
    which spreads out retries without ever exceeding the cap.
    """
    delay = min(cap, base * (2 ** attempt))
    if jitter_fraction > 0:
        delay = delay * (1.0 - jitter_fraction) + rng.uniform(0.0, delay * jitter_fraction)
    return delay


def fetch_with_retry(
    adapter: Adapter,
    keyword: str,
    page: int,
    retry_settings: dict,
    sleeper: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> tuple[RawResponse, int]:
    max_attempts = max(1, int(retry_settings.get("max_attempts", 3)))
    base_delay = max(0.0, float(retry_settings.get("base_delay_seconds", 0.5)))
    max_delay = max(base_delay, float(retry_settings.get("max_delay_seconds", 10)))
    budget = max(0.0, float(retry_settings.get("retry_after_budget_seconds", 30)))
    jitter = min(1.0, max(0.0, float(retry_settings.get("jitter_fraction", 0.0))))
    rng = rng or random.Random()
    retries = 0
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = adapter.fetch_page(keyword, page)
        except (TimeoutError, ConnectionError) as exc:
            last_error = exc
            if attempt >= max_attempts - 1:
                break
            delay = backoff_delay(attempt, base_delay, max_delay, jitter, rng)
            if delay > 0:
                sleeper(delay)
            retries += 1
            continue

        if response.http_status == 429:
            if attempt >= max_attempts - 1:
                return response, retries
            header = next((v for k, v in response.headers.items() if k.lower() == "retry-after"), None)
            delay = retry_after_seconds(header)
            if delay is None:
                delay = backoff_delay(attempt, base_delay, max_delay, jitter, rng)
            if delay > budget:
                return response, retries
            if delay > 0:
                sleeper(delay)
            retries += 1
            continue

        # Access denied/challenge responses must never be retried automatically.
        return response, retries

    raise FetchExhausted(f"Fetch failed after {max_attempts} attempts: {last_error or 'retry limit reached'}", retries)
