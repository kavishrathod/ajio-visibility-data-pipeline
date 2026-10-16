"""Serve previously stored raw snapshots so a failed load can be retried without refetching."""
from __future__ import annotations

import json
from pathlib import Path

from .base import Adapter, RawResponse


class ReplayAdapter(Adapter):
    """Reads ``*.meta.json`` sidecars written next to each raw snapshot.

    For one (keyword, page) the most recently fetched snapshot wins. It never
    touches the network.
    """

    def __init__(self, root: Path, scheduled_hour: str, platform: str = "AJIO") -> None:
        self.calls = 0
        self._items: dict[tuple[str, int], dict] = {}
        base = Path(root) / "data" / "raw" / f"platform={platform}"
        for meta_path in sorted(base.glob("date=*/hour=*/*/*.meta.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("scheduled_hour") != scheduled_hour:
                continue
            key = (meta["keyword"], int(meta["page"]))
            current = self._items.get(key)
            if current is None or meta["fetched_at"] >= current["meta"]["fetched_at"]:
                self._items[key] = {"meta": meta, "body_path": meta_path.with_name(meta_path.name[: -len(".meta.json")] + ".html")}

    @property
    def keywords(self) -> list[str]:
        return sorted({keyword for keyword, _ in self._items})

    def fetch_page(self, keyword: str, page: int) -> RawResponse:
        self.calls += 1
        item = self._items.get((keyword, page))
        if item is None:
            raise FileNotFoundError(f"No stored raw snapshot for keyword={keyword!r} page={page}")
        meta = item["meta"]
        return RawResponse(
            keyword=keyword, page=page, http_status=int(meta["http_status"]),
            body=Path(item["body_path"]).read_text(encoding="utf-8"),
            headers=dict(meta.get("headers") or {}), is_mock=bool(meta.get("is_mock", True)),
            fetched_at=meta["fetched_at"],
        )
