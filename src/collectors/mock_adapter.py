"""Synthetic fixture adapter. Every response is explicitly marked as mock data."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .base import Adapter, RawResponse
from .synthetic import render_page


class MockAdapter(Adapter):
    """Serve local HTML fixtures; never performs network calls.

    ``mapping`` maps keywords to fixture filenames. ``page_mapping`` may map
    ``(keyword, page)`` to a filename for targeted tests. Unmapped second pages
    return a genuine synthetic zero-result fixture so normal demos terminate.
    """

    def __init__(
        self,
        fixtures_dir: str | Path,
        mapping: Mapping[str, str] | None = None,
        page_mapping: Mapping[tuple[str, int], str] | None = None,
        generate: bool = False,
    ) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        self.mapping = dict(mapping or {})
        self.page_mapping = dict(page_mapping or {})
        self.generate = generate
        self.slot = "1970-01-01T00:00:00Z"

    def set_slot(self, scheduled_hour: str) -> None:
        self.slot = scheduled_hour

    def _fixture_name(self, keyword: str, page: int) -> str:
        if (keyword, page) in self.page_mapping:
            return self.page_mapping[(keyword, page)]
        if page > 1:
            return "zero_results.html"
        if keyword in self.mapping:
            return self.mapping[keyword]
        return "normal_results.html"

    def fetch_page(self, keyword: str, page: int) -> RawResponse:
        explicit = (keyword, page) in self.page_mapping or keyword in self.mapping
        if self.generate and not explicit:
            return RawResponse(
                keyword=keyword, page=page, http_status=200,
                body=render_page(keyword, page, self.slot),
                headers={"X-Data-Mode": "mock-generated"}, is_mock=True,
            )
        filename = self._fixture_name(keyword, page)
        path = self.fixtures_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Mock fixture not found: {path}")
        body = path.read_text(encoding="utf-8")
        if "SYNTHETIC MOCK FIXTURE" not in body:
            raise ValueError(f"Fixture {filename} is not visibly labelled as synthetic mock data")
        return RawResponse(
            keyword=keyword,
            page=page,
            http_status=200,
            body=body,
            headers={"X-Data-Mode": "mock"},
            is_mock=True,
        )
