"""Duplicate-spike measurement (Task E).

Every target records how many repeated placements it dropped in an hour (``target_hour_status.duplicate_count``;
the same-page and cross-page duplicates that deduplication removes). From that, one hour has:

* ``duplicates``  - repeated placements dropped across all targets;
* ``kept``        - placements kept (``row_count``);
* ``rate``        - duplicates / (kept + duplicates).

An hour is a *spike* when all three hold:

1. ``duplicates >= duplicate_spike_min_count``  (default 10): a handful of repeats is normal noise;
2. ``rate >= duplicate_spike_min_rate``         (default 2%): the repeats are a real share of the units seen;
3. ``rate >= duplicate_spike_multiplier x`` the rolling median rate of the previous complete hours (default 5x,
   median of up to ``duplicate_baseline_runs`` = 6 hours, used only once 3 such hours exist).

The baseline uses only earlier hours in which every target finished (``success`` or ``zero_result``) and recorded a
duplicate count, so incomplete or older hours never skew it. Without a baseline, rules 1 and 2 decide on their own.
"""
from __future__ import annotations

import statistics
from typing import Any

from src.storage.database import Database

DEFAULTS = {
    "duplicate_spike_min_count": 10,
    "duplicate_spike_min_rate": 0.02,
    "duplicate_spike_multiplier": 5.0,
    "duplicate_baseline_runs": 6,
}
MIN_BASELINE_HOURS = 3


def slot_duplicate_stats(db: Database, platform: str, hour: str) -> dict[str, Any]:
    """Duplicate counts for one hour, over enabled targets, plus which targets were affected."""
    rows = db.query(
        "SELECT t.target_value AS keyword, s.status, s.duplicate_count, s.row_count "
        "FROM target_hour_status s JOIN scrape_target t ON t.target_id=s.target_id "
        "WHERE s.platform=? AND s.scheduled_hour=? AND t.enabled=1 ORDER BY t.target_value",
        (platform, hour),
    )
    measured = [r for r in rows if r["duplicate_count"] is not None]
    duplicates = sum(int(r["duplicate_count"]) for r in measured)
    kept = sum(int(r["row_count"] or 0) for r in measured)
    seen = duplicates + kept
    return {
        "targets": len(rows),
        "measured_targets": len(measured),
        "running_targets": sum(1 for r in rows if r["status"] == "running"),
        "duplicates": duplicates,
        "kept": kept,
        "rate": (duplicates / seen) if seen else 0.0,
        "affected": sorted(
            ({"keyword": r["keyword"], "status": r["status"], "duplicates": int(r["duplicate_count"])} for r in measured if r["duplicate_count"]),
            key=lambda a: (-a["duplicates"], a["keyword"]),
        ),
    }


def baseline_rates(db: Database, platform: str, hour: str, expected_targets: int, limit: int) -> list[float]:
    """Duplicate rate of each of the most recent earlier hours in which every target finished and was measured."""
    rows = db.query(
        "SELECT SUM(s.duplicate_count) AS d, SUM(s.row_count) AS k FROM target_hour_status s "
        "JOIN scrape_target t ON t.target_id=s.target_id "
        "WHERE s.platform=? AND s.scheduled_hour<? AND t.enabled=1 "
        "GROUP BY s.scheduled_hour "
        "HAVING COUNT(*)=? AND SUM(s.duplicate_count IS NOT NULL)=COUNT(*) AND SUM(s.status IN ('success','zero_result'))=COUNT(*) "
        "ORDER BY s.scheduled_hour DESC LIMIT ?",
        (platform, hour, expected_targets, limit),
    )
    rates = []
    for r in rows:
        seen = int(r["d"] or 0) + int(r["k"] or 0)
        rates.append((int(r["d"] or 0) / seen) if seen else 0.0)
    return rates


def detect_duplicate_spike(db: Database, settings: dict[str, Any], platform: str, hour: str) -> dict[str, Any] | None:
    """Return the evidence for a spike in this hour, or None when there is none (or the hour is still running)."""
    cfg = {**DEFAULTS, **{k: v for k, v in (settings or {}).items() if k in DEFAULTS}}
    stats = slot_duplicate_stats(db, platform, hour)
    if not stats["targets"] or stats["running_targets"] or stats["measured_targets"] < stats["targets"]:
        return None  # nothing recorded, still running, or measured only in part: do not guess
    rates = baseline_rates(db, platform, hour, stats["targets"], int(cfg["duplicate_baseline_runs"]))
    baseline = statistics.median(rates) if len(rates) >= MIN_BASELINE_HOURS else None
    threshold = float(cfg["duplicate_spike_min_rate"])
    if baseline is not None:
        threshold = max(threshold, float(cfg["duplicate_spike_multiplier"]) * baseline)
    if stats["duplicates"] < int(cfg["duplicate_spike_min_count"]) or stats["rate"] < threshold:
        return None
    return {**stats, "threshold_rate": threshold, "baseline_rate": baseline, "baseline_hours": len(rates),
            "min_count": int(cfg["duplicate_spike_min_count"])}
