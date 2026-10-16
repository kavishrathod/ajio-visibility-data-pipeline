"""Target-hour completeness evaluation and missing-slot state materialization."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.storage.database import Database, utc_now_iso


def parse_hour(value: str | datetime | None = None) -> datetime:
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        normalized = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return dt


def format_hour(value: str | datetime | None = None) -> str:
    return parse_hour(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run_is_active(db: Database, run_id: str | None) -> bool:
    if not run_id:
        return False
    return bool(db.query("SELECT 1 FROM pipeline_lock WHERE run_id=?", (run_id,)))


def evaluate_completeness(
    db: Database,
    platform: str,
    scheduled_hour: str | datetime | None = None,
    grace_period_minutes: int = 15,
    threshold: float = 0.98,
    now: datetime | None = None,
) -> dict[str, Any]:
    hour = parse_hour(scheduled_hour)
    hour_text = format_hour(hour)
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    due = now_utc >= hour + timedelta(minutes=max(0, grace_period_minutes))
    targets = db.query("SELECT * FROM scrape_target WHERE platform=? AND enabled=1 ORDER BY target_id", (platform,))
    existing_rows = db.query(
        "SELECT * FROM target_hour_status WHERE platform=? AND scheduled_hour=?", (platform, hour_text)
    )
    existing = {int(r["target_id"]): r for r in existing_rows}
    checked_at = utc_now_iso()

    for target in targets:
        target_id = int(target["target_id"])
        old = existing.get(target_id)
        if old is None:
            status = "missing" if due else "not_yet_due"
            db.upsert_status({
                "platform": platform,
                "target_id": target_id,
                "scheduled_hour": hour_text,
                "status": status,
                "expected": 1,
                "observed": 0,
                "row_count": 0,
                "first_seen_at": checked_at,
                "checked_at": checked_at,
                "missing_reason": "No target-hour status found after grace period" if due else "Grace period has not elapsed",
                "incident_id": None,
                "last_run_id": None,
                "parse_error_count": 0,
                "is_mock": 1,
            })
        elif old["status"] == "not_yet_due" and due:
            db.upsert_status({
                "platform": platform,
                "target_id": target_id,
                "scheduled_hour": hour_text,
                "status": "missing",
                "expected": 1,
                "observed": 0,
                "row_count": 0,
                "first_seen_at": old.get("first_seen_at") or checked_at,
                "checked_at": checked_at,
                "missing_reason": "No target-hour status found after grace period",
                "incident_id": old.get("incident_id"),
                "last_run_id": old.get("last_run_id"),
                "parse_error_count": int(old.get("parse_error_count") or 0),
                "is_mock": 1,
            })
        elif old["status"] == "running" and due and not _run_is_active(db, old.get("last_run_id")):
            # The run that marked this slot 'running' is gone (crash, kill): the slot never reached a terminal state.
            db.upsert_status({
                "platform": platform, "target_id": target_id, "scheduled_hour": hour_text, "status": "missing",
                "expected": 1, "observed": 0, "row_count": 0, "first_seen_at": old.get("first_seen_at") or checked_at,
                "checked_at": checked_at, "missing_reason": "Run ended without a terminal status for this target",
                "incident_id": old.get("incident_id"), "last_run_id": old.get("last_run_id"),
                "parse_error_count": int(old.get("parse_error_count") or 0), "is_mock": 1,
            })
        elif old is not None:
            db.execute(
                "UPDATE target_hour_status SET checked_at=? WHERE platform=? AND target_id=? AND scheduled_hour=?",
                (checked_at, platform, target_id, hour_text),
            )

    status_rows = db.query(
        "SELECT s.*, t.target_value AS keyword FROM target_hour_status s "
        "JOIN scrape_target t ON t.target_id=s.target_id "
        "WHERE s.platform=? AND s.scheduled_hour=? AND t.enabled=1 ORDER BY t.target_value",
        (platform, hour_text),
    )
    total = len(targets)
    complete_statuses = {"success", "zero_result"}
    complete = sum(1 for row in status_rows if row["status"] in complete_statuses)
    pct = (complete / total) if total else 1.0
    incomplete = [
        {"keyword": row["keyword"], "status": row["status"], "reason": row.get("missing_reason")}
        for row in status_rows if row["status"] not in complete_statuses
    ]
    return {
        "platform": platform,
        "scheduled_hour": hour_text,
        "due": due,
        "expected_targets": total,
        "completed_targets": complete,
        "completeness_ratio": pct,
        "completeness_percent": round(pct * 100, 2),
        "threshold": threshold,
        "meets_threshold": (pct >= threshold) and due,
        "incomplete_targets": incomplete,
        "status_counts": {status: sum(1 for row in status_rows if row["status"] == status) for status in sorted({r["status"] for r in status_rows})},
    }
