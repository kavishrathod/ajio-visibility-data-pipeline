"""Task B/D: jittered exponential backoff and a minimum-interval rate limiter."""
import random

import pytest

from src.collectors.fetcher import backoff_delay, fetch_with_retry
from src.collectors.ratelimit import RateLimiter
from src.pipeline.orchestrator import run_pipeline
from tests.helpers import isolated_config
from tests.test_fetcher import SequenceAdapter, response


def test_backoff_without_jitter_is_pure_exponential_and_capped():
    rng = random.Random(0)
    assert [backoff_delay(a, 0.25, 5, 0.0, rng) for a in range(7)] == [0.25, 0.5, 1.0, 2.0, 4.0, 5, 5]


def test_backoff_jitter_stays_inside_the_documented_band():
    rng = random.Random(42)
    samples = [backoff_delay(2, 0.25, 5, 0.5, rng) for _ in range(2000)]
    assert min(samples) >= 0.5 and max(samples) <= 1.0  # [50%, 100%] of 1.0 s
    assert len({round(s, 6) for s in samples}) > 100  # genuinely randomised, not constant


def test_fetch_retry_sleeps_use_jitter_when_configured():
    adapter = SequenceAdapter([TimeoutError("t1"), TimeoutError("t2"), response(200)])
    slept = []
    result, retries = fetch_with_retry(adapter, "kw", 1, {"max_attempts": 3, "base_delay_seconds": 0.25, "max_delay_seconds": 5, "jitter_fraction": 0.5},
                                       sleeper=slept.append, rng=random.Random(7))
    assert result.http_status == 200 and retries == 2
    assert 0.125 <= slept[0] <= 0.25 and slept[0] != 0.25
    assert 0.25 <= slept[1] <= 0.5 and slept[1] != 0.5


def test_rate_limiter_enforces_minimum_interval_with_a_fake_clock():
    clock = {"t": 0.0}
    waits = []

    def sleeper(seconds):
        waits.append(seconds)
        clock["t"] += seconds

    limiter = RateLimiter(0.5, sleeper=sleeper, clock=lambda: clock["t"])  # one request per 2 s
    limiter.wait()                 # first request: immediate
    limiter.wait()                 # immediately again: must wait the full 2 s
    clock["t"] += 0.5              # half a second of "work"
    limiter.wait()                 # only 1.5 s remain
    clock["t"] += 5.0              # slower than the limit: no wait needed
    limiter.wait()
    assert waits == [2.0, 1.5]
    assert limiter.total_wait == 3.5


def test_rate_limiter_rejects_nonsense_rate():
    with pytest.raises(ValueError):
        RateLimiter(0)


def test_pipeline_paces_requests_when_rate_limit_applies_to_the_mock(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    config.settings["rate_limit"].update({"enabled": True, "apply_to_mock": True, "requests_per_second": 2})
    slept = []
    summary = run_pipeline(config, "2026-10-16T14:00:00Z", sleeper=slept.append)
    assert summary["status"] == "success"
    assert len(slept) == 1 and 0 < slept[0] <= 0.5  # 2 requests (pages 1 and 2) -> one wait of up to 1/2 s
    assert summary["rate_limit_wait_seconds"] > 0


def test_mock_is_not_rate_limited_by_default(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    config.settings["rate_limit"]["enabled"] = True  # apply_to_mock stays false
    slept = []
    run_pipeline(config, "2026-10-16T14:00:00Z", sleeper=slept.append)
    assert slept == []
