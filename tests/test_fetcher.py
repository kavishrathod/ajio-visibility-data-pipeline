from src.collectors.base import RawResponse
from src.collectors.fetcher import fetch_with_retry, retry_after_seconds


class SequenceAdapter:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def fetch_page(self, keyword, page):
        self.calls += 1
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def response(status, headers=None):
    return RawResponse("test", 1, status, "<html></html>", headers or {}, is_mock=True)


def test_429_retries_using_retry_after_then_succeeds():
    adapter = SequenceAdapter([response(429, {"Retry-After": "2"}), response(200)])
    slept = []
    result, retries = fetch_with_retry(
        adapter, "test", 1,
        {"max_attempts": 3, "base_delay_seconds": 0.1, "max_delay_seconds": 5, "retry_after_budget_seconds": 5},
        sleeper=slept.append,
    )
    assert result.http_status == 200
    assert retries == 1
    assert slept == [2.0]
    assert adapter.calls == 2


def test_403_is_returned_without_retry():
    adapter = SequenceAdapter([response(403), response(200)])
    result, retries = fetch_with_retry(adapter, "test", 1, {"max_attempts": 3}, sleeper=lambda _: None)
    assert result.http_status == 403
    assert retries == 0
    assert adapter.calls == 1


def test_timeout_retries_with_bounded_backoff():
    adapter = SequenceAdapter([TimeoutError("temporary"), response(200)])
    slept = []
    result, retries = fetch_with_retry(
        adapter, "test", 1,
        {"max_attempts": 3, "base_delay_seconds": 0.25, "max_delay_seconds": 1},
        sleeper=slept.append,
    )
    assert result.http_status == 200
    assert retries == 1
    assert slept == [0.25]


def test_retry_after_parses_seconds_and_rejects_bad_values():
    assert retry_after_seconds("3") == 3.0
    assert retry_after_seconds("bad") is None
    assert retry_after_seconds(None) is None
