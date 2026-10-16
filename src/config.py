"""Configuration loading and validation."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    root: Path
    settings: dict[str, Any]
    targets: dict[str, Any]
    db_path: Path

    @property
    def platform(self) -> str:
        return str(self.targets.get("platform", "AJIO"))

    @property
    def platform_code(self) -> str:
        return str(self.targets.get("platform_code", self.platform))

    @property
    def keywords(self) -> list[str]:
        return list(self.targets.get("keywords", []))

    @property
    def max_pages(self) -> int:
        return max(1, int(self.settings.get("max_pages", self.targets.get("max_pages", 1))))


def load_config(root: str | Path | None = None) -> AppConfig:
    """Load project config, check the target list, and resolve the SQLite path."""
    project_root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    load_dotenv(project_root / ".env", override=False)

    settings_path = project_root / "config" / "settings.yaml"
    targets_path = project_root / "config" / "targets.json"
    if not settings_path.is_file():
        raise FileNotFoundError(f"Missing settings file: {settings_path}")
    if not targets_path.is_file():
        raise FileNotFoundError(f"Missing targets file: {targets_path}")

    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    targets = json.loads(targets_path.read_text(encoding="utf-8"))
    keywords = targets.get("keywords", [])
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("config/targets.json must contain a non-empty keywords array")
    normalized = [str(item).strip() for item in keywords]
    if any(not item for item in normalized):
        raise ValueError("Target keywords cannot be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("Target keywords must be unique")
    targets["keywords"] = normalized

    db_setting = os.getenv("DB_PATH", "data/pipeline.db")
    db_path = Path(db_setting).expanduser()
    if not db_path.is_absolute():
        db_path = project_root / db_path

    settings.setdefault("adapter", "mock")
    if settings["adapter"] not in {"mock", "live"}:
        raise ValueError("settings.adapter must be 'mock' or 'live'")
    settings.setdefault("retries", {})
    settings.setdefault("grace_period_minutes", 15)
    settings.setdefault("completeness_threshold", 0.98)
    settings.setdefault("alerts", {"cooldown_minutes": 60})
    return AppConfig(project_root, settings, targets, db_path.resolve())
