"""Task C/E: raw partition layout, running/missing states, migration, malformed payloads."""
import json
import sqlite3
from datetime import datetime, timezone

from src.parsers.product_parser import parse_products
from src.pipeline.completeness import evaluate_completeness
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOUR = "2026-10-16T14:00:00Z"


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


def test_raw_snapshots_use_platform_date_hour_partitions_with_a_metadata_sidecar(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    summary = run_pipeline(config, HOUR, sleeper=no_sleep)
    db = _db(config)
    row = db.query("SELECT raw_payload_ref FROM visibility_product LIMIT 1")[0]
    prefix = f"data/raw/platform=AJIO/date=2026-10-16/hour=14/{summary['run_id']}/"
    assert row["raw_payload_ref"] == prefix + "men_black_jeans__p1.html"
    body = (config.root / row["raw_payload_ref"]).read_text(encoding="utf-8")
    assert "SYNTHETIC MOCK FIXTURE" in body
    meta = json.loads((config.root / (prefix + "men_black_jeans__p1.meta.json")).read_text())
    assert meta["scheduled_hour"] == HOUR and meta["keyword"] == "men black jeans" and meta["page"] == 1 and meta["http_status"] == 200
    snapshot = db.query("SELECT body_path, sha256 FROM raw_snapshot WHERE page_number=1")[0]
    assert snapshot["body_path"] == row["raw_payload_ref"] and snapshot["sha256"] == meta["sha256"]


def test_target_status_is_running_while_the_target_is_being_fetched(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    db = _db(config)
    seen = []

    def fn(keyword, page, n):
        seen.append(db.query("SELECT status FROM target_hour_status")[0]["status"])
        return resp(fixture_text("small_page.html")) if page == 1 else resp(fixture_text("zero_results.html"), page=2)

    run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)
    assert seen == ["running", "running"]
    assert db.query("SELECT status FROM target_hour_status")[0]["status"] == "success"


def test_orphaned_running_slot_becomes_missing_but_a_live_run_is_left_alone(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    db = _db(config)
    target = db.query("SELECT target_id FROM scrape_target")[0]["target_id"]
    db.create_run({"run_id": "r1", "platform": "AJIO", "scheduled_hour": HOUR, "started_at": "2026-10-16T14:00:05Z", "finished_at": None,
                   "status": "running", "trigger": "scheduled", "expected_target_count": 1, "completed_target_count": 0, "row_count": 0,
                   "error_count": 0, "retry_count": 0, "scraper_version": "x", "adapter_mode": "mock", "error_summary": None})
    db.upsert_status({"platform": "AJIO", "target_id": target, "scheduled_hour": HOUR, "status": "running", "expected": 1, "observed": 0,
                      "row_count": 0, "first_seen_at": "2026-10-16T14:00:05Z", "checked_at": "2026-10-16T14:00:05Z", "missing_reason": None,
                      "incident_id": None, "last_run_id": "r1", "parse_error_count": 0, "is_mock": 1})
    due = datetime(2026, 10, 16, 14, 30, tzinfo=timezone.utc)
    db.acquire_lock("pipeline:AJIO", "r1")
    assert evaluate_completeness(db, "AJIO", HOUR, 15, 0.98, now=due)["status_counts"] == {"running": 1}
    db.release_lock("pipeline:AJIO", "r1")
    result = evaluate_completeness(db, "AJIO", HOUR, 15, 0.98, now=due)
    assert result["status_counts"] == {"missing": 1}
    assert "without a terminal status" in db.query("SELECT missing_reason FROM target_hour_status")[0]["missing_reason"]


def test_older_database_without_new_columns_is_upgraded(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.db_path)
    conn.executescript("CREATE TABLE alert_incident (incident_id TEXT PRIMARY KEY, alert_type TEXT NOT NULL, severity TEXT NOT NULL, "
                       "affected_targets TEXT NOT NULL DEFAULT '[]', scheduled_hour TEXT NOT NULL, opened_at TEXT NOT NULL, last_sent_at TEXT, "
                       "send_count INTEGER NOT NULL DEFAULT 0, resolved_at TEXT, recovery_sent_at TEXT, details TEXT);")
    conn.close()
    db = Database(config.db_path, config.root)
    db.initialize()
    columns = {r["name"] for r in db.query("PRAGMA table_info(alert_incident)")}
    assert {"run_id", "fingerprint", "conditions", "last_error"} <= columns
    assert "anomalies" in {r["name"] for r in db.query("PRAGMA table_info(target_hour_status)")}


def test_malformed_payloads_are_parse_failures_not_empty_results():
    for body in ("", "<<<not html>>>", "{\"products\": [", "<html><body><section data-testid=\"product-grid\"><article class=\"product-card\">", "\x00\x01\x02"):
        result = parse_products(body)
        assert result.status == "parse_failed", body
        assert result.units == []


def test_unexpected_server_error_is_a_parse_failure(tmp_path):
    result = parse_products("<html>oops</html>", http_status=503)
    assert result.status == "parse_failed" and "503" in result.reason
