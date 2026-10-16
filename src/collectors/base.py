"""Adapter contract and raw response model."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class RawResponse:
    keyword: str
    page: int
    http_status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    is_mock: bool = False
    fetched_at: str = field(default_factory=utc_now_iso)


class Adapter(ABC):
    """A source adapter. Retry policy is deliberately kept outside adapters."""

    def set_slot(self, scheduled_hour: str) -> None:
        """Tell the adapter which scheduled hour is being collected (optional hook)."""

    @abstractmethod
    def fetch_page(self, keyword: str, page: int) -> RawResponse:
        """Fetch a single page; raise TimeoutError for simulated/network timeouts."""
