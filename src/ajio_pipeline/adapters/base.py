from __future__ import annotations
from abc import ABC, abstractmethod
from ..models import RawResponse


class Adapter(ABC):
    """Single seam between 'where pages come from' and the rest of the pipeline.

    The parser, storage, scheduler and monitoring never import a concrete adapter.
    """

    @abstractmethod
    def fetch_page(self, keyword: str, page: int) -> RawResponse:
        """Return the raw response for (keyword, page).

        Must raise TimeoutError on timeout; must NOT retry internally
        (retry/backoff belongs to the fetcher so it is testable in one place).
        """
