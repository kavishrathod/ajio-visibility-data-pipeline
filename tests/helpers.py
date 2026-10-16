from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.collectors.base import Adapter, RawResponse
from src.config import load_config

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def isolated_config(tmp_path: Path, keywords: list[str] | None = None, stale_sla_minutes: int = 0):
    """A throw-away project copy. ``stale_sla_minutes=0`` switches the stale trigger off so tests stay deterministic."""
    root = tmp_path / "ajio-project"
    (root / "config").mkdir(parents=True)
    (root / "sql").mkdir(parents=True)
    (root / "tests" / "fixtures").mkdir(parents=True)
    project_root = Path(__file__).resolve().parents[1]
    shutil.copy2(project_root / "config" / "settings.yaml", root / "config" / "settings.yaml")
    targets = json.loads((project_root / "config" / "targets.json").read_text(encoding="utf-8"))
    if keywords is not None:
        targets["keywords"] = keywords
        targets["expected_zero_result_keywords"] = [kw for kw in keywords if kw in {"zxqvbn shirt", "asdfgh qwerty zzzz"}]
    (root / "config" / "targets.json").write_text(json.dumps(targets, indent=2), encoding="utf-8")
    shutil.copy2(project_root / "sql" / "schema.sql", root / "sql" / "schema.sql")
    for fixture in (project_root / "tests" / "fixtures").glob("*.html"):
        shutil.copy2(fixture, root / "tests" / "fixtures" / fixture.name)
    config = load_config(root)
    config.settings.setdefault("alerts", {})["stale_sla_minutes"] = stale_sla_minutes
    config.settings.setdefault("rate_limit", {})["enabled"] = False  # politeness has its own tests
    return config


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def resp(body: str, status: int = 200, headers: dict | None = None, fetched_at: str | None = None, keyword: str = "kw", page: int = 1) -> RawResponse:
    kwargs = {"fetched_at": fetched_at} if fetched_at else {}
    return RawResponse(keyword, page, status, body, headers or {}, is_mock=True, **kwargs)


class ScriptedAdapter(Adapter):
    """Adapter driven by a function ``fn(keyword, page, call_number) -> RawResponse`` (may raise)."""

    def __init__(self, fn):
        self.fn = fn
        self.calls: list[tuple[str, int]] = []

    def fetch_page(self, keyword: str, page: int) -> RawResponse:
        self.calls.append((keyword, page))
        return self.fn(keyword, page, len(self.calls))


class FakeMailer:
    """Records alert emails instead of sending them. ``ok=False`` simulates a delivery failure."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[tuple[str, str]] = []

    def send(self, subject: str, body: str) -> bool:
        if not self.ok:
            return False
        self.sent.append((subject, body))
        return True

    @property
    def subjects(self) -> list[str]:
        return [s for s, _ in self.sent]


def no_sleep(_seconds: float) -> None:
    return None
