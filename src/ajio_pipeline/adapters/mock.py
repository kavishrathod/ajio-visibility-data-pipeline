"""MockAdapter: serves saved fixtures. EVERY response is labelled is_mock=True.

Fixture file layout (tests/fixtures/<name>.json), see docs/fixture_format.md:
{
  "_mock": true,
  "scenario": "I-3",
  "keyword": "men white sneakers",
  "page": 1,
  "http": {"status": 200, "headers": {}, "raise": null},   # raise: "timeout" to simulate
  "body": "<string, usually JSON text of the simulated page>"
}
"""
from __future__ import annotations
import json
from pathlib import Path
from .base import Adapter
from ..models import RawResponse


class MockAdapter(Adapter):
    def __init__(self, fixtures_dir: str | Path, mapping: dict | None = None):
        # mapping: {(keyword, page): "fixture_filename.json"}; falls back to <slug>_p<page>.json
        self.dir = Path(fixtures_dir)
        self.mapping = mapping or {}

    def _path(self, keyword: str, page: int) -> Path:
        name = self.mapping.get((keyword, page))
        if name is None:
            slug = keyword.lower().replace(" ", "_")
            name = f"{slug}_p{page}.json"
        return self.dir / name

    def fetch_page(self, keyword: str, page: int) -> RawResponse:
        fx = json.loads(self._path(keyword, page).read_text(encoding="utf-8"))
        if not fx.get("_mock"):
            raise ValueError("fixture must declare \"_mock\": true")
        http = fx.get("http", {})
        if http.get("raise") == "timeout":
            raise TimeoutError("simulated timeout")
        return RawResponse(
            keyword=keyword, page=page,
            http_status=http.get("status", 200),
            body=fx["body"], headers=http.get("headers", {}),
            is_mock=True,
        )
