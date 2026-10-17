"""Audit: every status the brief asks the monitoring to distinguish is produced by real behaviour.

The brief lists: success, partial, failed, blocked, missing, zero-result, running and not-yet-due.
parse_failed is the extra status this project adds so a silent layout change is not a zero result.
Statuses come from page content and fetch outcomes, never from a process exit code.
"""
from datetime import datetime, timezone

from src.pipeline.completeness import evaluate_completeness
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOUR = "2026-10-16T14:30:00Z"
KEYWORDS = ["k success", "k zero", "k layout", "k blocked", "k failed", "k partial"]


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


def test_every_required_status_is_produced_by_the_pipeline_and_the_completeness_check(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS)
    db = _db(config)
    seen_while_fetching = {}

    def fn(keyword, page, n):
        if page == 1 and keyword == "k success":
            seen_while_fetching["status"] = db.query(
                "SELECT s.status FROM target_hour_status s JOIN scrape_target t USING(target_id) WHERE t.target_value=?",
                (keyword,))[0]["status"]
        if keyword == "k success":
            return resp(fixture_text("small_page.html")) if page == 1 else resp(fixture_text("zero_results.html"), page=2)
        if keyword == "k zero":
            return resp(fixture_text("zero_results.html"))
        if keyword == "k layout":
            return resp(fixture_text("layout_changed.html"))          # HTTP 200, grid missing
        if keyword == "k blocked":
            return resp("Forbidden", 403)
        if keyword == "k failed":
            raise TimeoutError("simulated read timeout")               # no page ever fetched
        if keyword == "k partial":
            if page == 1:
                return resp(fixture_text("small_page.html"))
            raise TimeoutError("simulated read timeout")               # page 1 fine, page 2 never arrives
        raise AssertionError(keyword)

    summary = run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)
    states = {r["keyword"]: r for r in db.query(
        "SELECT t.target_value AS keyword, s.status, s.row_count, s.observed FROM target_hour_status s JOIN scrape_target t USING(target_id)")}

    assert {k: v["status"] for k, v in states.items()} == {
        "k success": "success", "k zero": "zero_result", "k layout": "parse_failed",
        "k blocked": "blocked", "k failed": "failed", "k partial": "partial",
    }
    assert seen_while_fetching["status"] == "running"
    # Only success and zero_result count as observed/complete; partial keeps its page-1 rows but is not complete.
    assert {k: v["observed"] for k, v in states.items()} == {
        "k success": 1, "k zero": 1, "k layout": 0, "k blocked": 0, "k failed": 0, "k partial": 0}
    assert states["k partial"]["row_count"] == 2 and states["k failed"]["row_count"] == 0
    assert summary["status"] == "partial" and summary["completed_targets"] == 2
    assert summary["status_counts"] == {"success": 1, "zero_result": 1, "parse_failed": 1, "blocked": 1, "failed": 1, "partial": 1}


def test_not_yet_due_then_missing_for_an_hour_nobody_collected(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS)
    db = _db(config)
    never_run = "2026-10-16T15:30:00Z"
    early = evaluate_completeness(db, config.platform, never_run, 15, 0.98,
                                  now=datetime(2026, 10, 16, 15, 40, tzinfo=timezone.utc))
    assert early["status_counts"] == {"not_yet_due": 6} and early["due"] is False
    late = evaluate_completeness(db, config.platform, never_run, 15, 0.98,
                                 now=datetime(2026, 10, 16, 15, 50, tzinfo=timezone.utc))
    assert late["status_counts"] == {"missing": 6} and late["due"] is True
    assert late["completed_targets"] == 0
