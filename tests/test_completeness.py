from datetime import datetime, timezone

from src.pipeline.completeness import evaluate_completeness
from src.storage.database import Database
from tests.helpers import isolated_config


def test_completeness_waits_for_grace_then_marks_missing_slots(tmp_path):
    config = isolated_config(tmp_path, ["men white sneakers", "zxqvbn shirt"])
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    hour = "2026-10-16T14:30:00Z"

    early = evaluate_completeness(db, config.platform, hour, 15, 0.98, now=datetime(2026, 10, 16, 14, 40, tzinfo=timezone.utc))
    assert early["due"] is False
    assert early["status_counts"]["not_yet_due"] == 2

    due = evaluate_completeness(db, config.platform, hour, 15, 0.98, now=datetime(2026, 10, 16, 14, 50, tzinfo=timezone.utc))
    assert due["due"] is True
    assert due["status_counts"]["missing"] == 2
    assert due["completeness_percent"] == 0
    assert due["meets_threshold"] is False

    rows = db.query("SELECT target_id FROM scrape_target ORDER BY target_id")
    db.execute("UPDATE target_hour_status SET status='success',observed=3,row_count=3 WHERE target_id=?", (rows[0]["target_id"],))
    db.execute("UPDATE target_hour_status SET status='zero_result',observed=0,row_count=0 WHERE target_id=?", (rows[1]["target_id"],))
    recovered = evaluate_completeness(db, config.platform, hour, 15, 0.98, now=datetime(2026, 10, 16, 14, 50, tzinfo=timezone.utc))
    assert recovered["completeness_percent"] == 100
    assert recovered["meets_threshold"] is True
