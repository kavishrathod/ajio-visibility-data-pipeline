"""Curveball scenarios I-4 and I-7 .. I-12. (I-1/2/3/5/6 live in test_parsing.py, test_ranking.py, test_curveball_audit.py.)

Each test builds a fixture or simulated response and asserts exact values, so it fails if the handling is removed.
"""
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.collectors.mock_adapter import MockAdapter
from src.monitoring.alerts import check_hour
from src.pipeline.completeness import format_hour
from src.pipeline.orchestrator import reload_raw, run_pipeline
from src.storage.database import Database
from src.timeutil import ist_label
from tests.helpers import FakeMailer, ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOUR = "2026-10-16T14:00:00Z"
DUE = datetime(2026, 10, 16, 14, 20, tzinfo=timezone.utc)


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


# ---------------------------------------------------------------- I-4 pagination drift
def test_i4_pagination_drift_keeps_first_occurrence_and_records_anomaly(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    adapter = MockAdapter(config.root / "tests" / "fixtures", page_mapping={
        ("men black jeans", 1): "pagination_drift_page1.html", ("men black jeans", 2): "pagination_drift_page2.html"})
    summary = run_pipeline(config, HOUR, adapter_override=adapter, sleeper=no_sleep)
    db = _db(config)
    rows = db.query("SELECT product_id, absolute_rank, relative_rank, page_number FROM visibility_product ORDER BY absolute_rank")
    # Item C is on both pages: the page-1 placement is kept; D follows directly, so ranks stay continuous.
    assert [(r["product_id"], r["absolute_rank"], r["page_number"]) for r in rows] == [("111", 1, 1), ("222", 2, 1), ("333", 3, 1), ("444", 4, 2)]
    assert summary["status"] == "success" and summary["pagination_anomalies"] == 1
    status = db.query("SELECT anomalies FROM target_hour_status")[0]["anomalies"]
    assert json.loads(status) == [{"product_id": "333", "product_type": "Organic", "kept_on_page": 1, "repeated_on_page": 2}]


def test_i4_no_anomaly_for_clean_pagination(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    summary = run_pipeline(config, HOUR, adapter_override=MockAdapter(config.root / "tests" / "fixtures", generate=True), sleeper=no_sleep)
    assert summary["pagination_anomalies"] == 0
    assert _db(config).query("SELECT anomalies FROM target_hour_status")[0]["anomalies"] is None


# ---------------------------------------------------------------- I-7 throttled and blocked
def _one_then_zero(first_page_response):
    def fn(keyword, page, n):
        return first_page_response() if page == 1 else resp(fixture_text("zero_results.html"), page=2)
    return fn


def test_i7_429_waits_for_retry_after_within_budget(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    queue = [resp("", 429, {"Retry-After": "3"}), resp(fixture_text("small_page.html"))]
    adapter = ScriptedAdapter(lambda kw, page, n: queue.pop(0) if page == 1 else resp(fixture_text("zero_results.html"), page=2))
    slept = []
    summary = run_pipeline(config, HOUR, adapter_override=adapter, sleeper=slept.append)
    assert slept == [3.0]  # exactly what Retry-After asked for
    assert summary["status"] == "success" and summary["retry_count"] == 1 and summary["rows_written_or_upserted"] == 2


def test_i7_429_beyond_budget_marks_target_blocked_without_waiting(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    adapter = ScriptedAdapter(lambda kw, page, n: resp("", 429, {"Retry-After": "3600"}))
    slept = []
    summary = run_pipeline(config, HOUR, adapter_override=adapter, sleeper=slept.append)
    status = _db(config).query("SELECT status, missing_reason FROM target_hour_status")[0]
    assert slept == [] and len(adapter.calls) == 1
    assert status["status"] == "blocked" and "429" in status["missing_reason"]
    assert summary["status"] == "failed"


def test_i7_403_stops_that_target_marks_blocked_and_alerts(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans", "women handbag"])

    def fn(keyword, page, n):
        if keyword == "men black jeans":
            return resp("Forbidden", 403)
        return resp(fixture_text("small_page.html")) if page == 1 else resp(fixture_text("zero_results.html"), page=2)

    adapter = ScriptedAdapter(fn)
    slept = []
    summary = run_pipeline(config, HOUR, adapter_override=adapter, sleeper=slept.append)
    assert [c for c in adapter.calls if c[0] == "men black jeans"] == [("men black jeans", 1)]  # no retry, no evasion
    assert slept == []
    db = _db(config)
    states = {r["keyword"]: r["status"] for r in db.query("SELECT t.target_value AS keyword, s.status FROM target_hour_status s JOIN scrape_target t USING(target_id)")}
    assert states == {"men black jeans": "blocked", "women handbag": "success"}  # other target continues
    assert summary["status"] == "partial"
    mailer = FakeMailer()
    result = check_hour(db, config, HOUR, now=DUE, mailer=mailer)
    assert "blocked" in result["conditions"]
    assert mailer.sent[0][0].startswith("[AJIO VISIBILITY][CRITICAL] Target blocked")
    assert "- men black jeans: blocked" in mailer.sent[0][1]


def test_i7_bot_challenge_page_with_http_200_is_blocked_not_zero_result(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(lambda *a: resp(fixture_text("bot_challenge.html"))), sleeper=no_sleep)
    db = _db(config)
    assert db.query("SELECT status FROM target_hour_status")[0]["status"] == "blocked"
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product")[0]["n"] == 0


# ---------------------------------------------------------------- I-8 hour boundary
def test_i8_late_run_keeps_its_scheduled_slot(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    # The slot is 10:00 UTC. Pages are fetched at 11:00:40 UTC, after the boundary.
    late = ScriptedAdapter(lambda kw, page, n: resp(fixture_text("small_page.html"), fetched_at="2026-10-16T11:00:40Z") if page == 1 else resp(fixture_text("zero_results.html"), fetched_at="2026-10-16T11:00:41Z", page=2))
    summary = run_pipeline(config, "2026-10-16T10:59:58Z", adapter_override=late, sleeper=no_sleep)
    db = _db(config)
    rows = db.query("SELECT scheduled_hour, time_stamp FROM visibility_product")
    assert summary["scheduled_hour"] == "2026-10-16T10:00:00Z"
    assert {(r["scheduled_hour"], r["time_stamp"]) for r in rows} == {("2026-10-16T10:00:00Z", "2026-10-16T11:00:40Z")}
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product WHERE scheduled_hour='2026-10-16T11:00:00Z'")[0]["n"] == 0
    assert db.query("SELECT scheduled_hour FROM target_hour_status")[0]["scheduled_hour"] == "2026-10-16T10:00:00Z"


def test_i8_ist_input_maps_to_the_correct_utc_slot():
    assert format_hour("2026-10-16T16:29:58+05:30") == "2026-10-16T10:00:00Z"  # 10:59:58 UTC
    assert ist_label("2026-10-16T10:00:00Z") == "2026-10-16 15:30 IST"


# ---------------------------------------------------------------- I-9 overlapping runs
def test_i9_second_run_is_recorded_as_skipped_while_first_is_running(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    entered, gate = threading.Event(), threading.Event()
    calls = []

    def slow(keyword, page, n):
        calls.append((keyword, page))
        entered.set()
        assert gate.wait(10), "gate never opened"
        return resp(fixture_text("small_page.html")) if page == 1 else resp(fixture_text("zero_results.html"), page=2)

    first = {}
    worker = threading.Thread(target=lambda: first.update(run_pipeline(config, "2026-10-16T10:00:00Z", trigger="scheduled", adapter_override=ScriptedAdapter(slow), sleeper=no_sleep)))
    worker.start()
    assert entered.wait(10)
    second = run_pipeline(config, "2026-10-16T11:00:00Z", trigger="scheduled", adapter_override=ScriptedAdapter(slow), sleeper=no_sleep)
    assert second["status"] == "skipped_overlap" and second["rows_written_or_upserted"] == 0
    assert calls == [("men black jeans", 1)]  # the second run never fetched the target
    gate.set()
    worker.join(10)
    assert first["status"] == "success"
    db = _db(config)
    runs = {r["scheduled_hour"]: r for r in db.query("SELECT * FROM scrape_run")}
    assert runs["2026-10-16T10:00:00Z"]["status"] == "success"
    assert runs["2026-10-16T11:00:00Z"]["status"] == "skipped_overlap"
    assert first["run_id"] in runs["2026-10-16T11:00:00Z"]["error_summary"]
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product WHERE scheduled_hour='2026-10-16T11:00:00Z'")[0]["n"] == 0


def test_i9_skipped_slot_shows_up_as_missing_and_alerts(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    db = _db(config)
    db.acquire_lock("pipeline:AJIO", "some-other-run")
    skipped = run_pipeline(config, HOUR, sleeper=no_sleep)
    assert skipped["status"] == "skipped_overlap"
    db.release_lock("pipeline:AJIO", "some-other-run")
    mailer = FakeMailer()
    result = check_hour(db, config, HOUR, now=DUE, mailer=mailer)
    assert result["conditions"] == ["missing_slots", "completeness"]
    assert run_pipeline(config, HOUR, sleeper=no_sleep)["status"] == "success"  # lock is free again


# ---------------------------------------------------------------- I-10 late backfill
def test_i10_late_backfill_fills_slot_resolves_alert_and_sends_one_recovery(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    db = _db(config)
    mailer = FakeMailer()
    nine = "2026-10-16T09:00:00Z"
    assert check_hour(db, config, nine, now=datetime(2026, 10, 16, 13, 0, tzinfo=timezone.utc), mailer=mailer)["alert_state"] == "sent"
    assert db.query("SELECT status FROM target_hour_status")[0]["status"] == "missing"

    first = run_pipeline(config, nine, trigger="backfill", sleeper=no_sleep)
    count = db.query("SELECT COUNT(*) AS n FROM visibility_product")[0]["n"]
    run_pipeline(config, nine, trigger="backfill", sleeper=no_sleep)  # a second backfill must not duplicate
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product")[0]["n"] == count > 0
    assert {r["scheduled_hour"] for r in db.query("SELECT scheduled_hour FROM visibility_product")} == {nine}
    assert first["trigger"] == "backfill"

    assert check_hour(db, config, nine, now=datetime(2026, 10, 16, 13, 5, tzinfo=timezone.utc), mailer=mailer)["alert_state"] == "resolved"
    assert check_hour(db, config, nine, now=datetime(2026, 10, 16, 13, 6, tzinfo=timezone.utc), mailer=mailer)["alert_state"] == "healthy"
    assert sum("[RECOVERED]" in s for s in mailer.subjects) == 1 and len(mailer.sent) == 2


# ---------------------------------------------------------------- I-11 database down mid-run
def _database_outage(monkeypatch):
    state = {"down": True}

    def wrap(name):
        original = getattr(Database, name)

        def guarded(self, *args, **kwargs):
            if state["down"]:
                raise sqlite3.OperationalError("unable to open database file")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Database, name, guarded)

    for method in ("save_raw_snapshot", "sync_products", "upsert_status"):
        wrap(method)
    return state


def test_i11_outage_keeps_raw_snapshots_and_reload_needs_no_refetch(tmp_path, monkeypatch):
    config = isolated_config(tmp_path, ["men black jeans", "zxqvbn shirt"])
    state = _database_outage(monkeypatch)
    summary = run_pipeline(config, HOUR, sleeper=no_sleep)
    assert summary["status"] == "failed" and summary["completed_targets"] == 0
    assert summary["db_errors"] and "load_failed" in summary["errors"][0]

    raw_dir = config.root / "data" / "raw" / "platform=AJIO" / "date=2026-10-16" / "hour=14"
    assert len(list(raw_dir.rglob("*.html"))) == 3 and len(list(raw_dir.rglob("*.meta.json"))) == 3  # 2 pages + 1 zero-result page
    db = _db(config)
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product")[0]["n"] == 0
    failed_run = db.query("SELECT status, error_summary FROM scrape_run")[0]
    assert failed_run["status"] == "failed" and "database" in failed_run["error_summary"]
    original_fetch_times = {json.loads(p.read_text())["fetched_at"] for p in raw_dir.rglob("*.meta.json")}

    state["down"] = False

    def refetch(self, keyword, page):
        raise AssertionError("reload must not fetch again")

    monkeypatch.setattr(MockAdapter, "fetch_page", refetch)
    reloaded = reload_raw(config, HOUR)
    assert reloaded["status"] == "success" and reloaded["completed_targets"] == 2 and reloaded["trigger"] == "reload"
    rows = db.query("SELECT time_stamp FROM visibility_product")
    assert len(rows) == 35 and {r["time_stamp"] for r in rows} <= original_fetch_times  # original fetch times preserved
    reload_raw(config, HOUR)
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product")[0]["n"] == 35  # reload is idempotent
    assert {r["status"] for r in db.query("SELECT status FROM target_hour_status")} == {"success", "zero_result"}


def test_i11_lock_left_behind_by_a_finished_run_does_not_block_the_next_run(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    db = _db(config)
    db.create_run({"run_id": "dead-run", "platform": "AJIO", "scheduled_hour": HOUR, "started_at": "2026-10-16T14:00:00Z",
                   "finished_at": "2026-10-16T14:01:00Z", "status": "failed", "trigger": "scheduled", "expected_target_count": 1,
                   "completed_target_count": 0, "row_count": 0, "error_count": 1, "retry_count": 0, "scraper_version": "x",
                   "adapter_mode": "mock", "error_summary": None})
    db.acquire_lock("pipeline:AJIO", "dead-run")  # the release failed while the database was down
    assert run_pipeline(config, HOUR, sleeper=no_sleep)["status"] == "success"


# ---------------------------------------------------------------- I-12 alert storm
def test_i12_forty_failures_produce_one_aggregated_email(tmp_path):
    config = isolated_config(tmp_path)  # all 50 configured keywords
    failing = set(config.keywords[:40])
    inner = MockAdapter(config.root / "tests" / "fixtures", mapping=config.settings["mock_fixtures"], generate=True)

    def fn(keyword, page, n):
        if keyword in failing:
            raise TimeoutError("simulated outage")
        return inner.fetch_page(keyword, page)

    summary = run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)
    assert summary["status"] == "partial" and summary["completed_targets"] == 10 and summary["status_counts"]["failed"] == 40
    db, mailer = _db(config), FakeMailer()
    first = check_hour(db, config, HOUR, now=DUE, mailer=mailer)
    assert first["conditions"] == ["completeness"] and first["alert_state"] == "sent"
    assert len(mailer.sent) == 1 and "Affected targets (40):" in mailer.sent[0][1] and "and 15 more" in mailer.sent[0][1]

    for minutes in (1, 2, 3):
        assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=minutes), mailer=mailer)["alert_state"] == "aggregated"
    assert len(mailer.sent) == 1  # repeated checks: no resend

    db.execute("UPDATE target_hour_status SET status='blocked' WHERE target_id=(SELECT MIN(target_id) FROM target_hour_status WHERE status='failed')")
    assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=4), mailer=mailer)["alert_state"] == "sent"  # status change
    assert len(mailer.sent) == 2
    assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=70), mailer=mailer)["alert_state"] == "reminder_sent"  # cooldown over
    assert len(mailer.sent) == 3
    assert db.query("SELECT COUNT(*) AS n FROM alert_incident")[0]["n"] == 1
