"""Alert triggers, email content and the incident lifecycle (Task G)."""
from datetime import datetime, timedelta, timezone

from src.collectors.mock_adapter import MockAdapter
from src.monitoring.alerts import check_hour
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import FakeMailer, ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOUR = "2026-10-16T14:30:00Z"
DUE = datetime(2026, 10, 16, 14, 50, tzinfo=timezone.utc)


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


def _timeout_adapter():
    def fn(keyword, page, n):
        raise TimeoutError("simulated read timeout")
    return ScriptedAdapter(fn)


def test_run_failed_alert_has_all_required_email_fields(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans", "women handbag"])
    summary = run_pipeline(config, HOUR, adapter_override=_timeout_adapter(), sleeper=no_sleep)
    assert summary["status"] == "failed"
    mailer = FakeMailer()
    result = check_hour(_db(config), config, HOUR, now=DUE, mailer=mailer)
    assert result["conditions"][0] == "run_failed"
    assert result["alert_state"] == "sent"
    subject, body = mailer.sent[0]
    assert subject == "[AJIO VISIBILITY][CRITICAL] Run failed — 2026-10-16 14:30 UTC (2026-10-16 20:00 IST)"
    assert "Platform:             AJIO" in body
    assert f"Run ID:               {summary['run_id']}" in body
    assert "0 observed complete" in body and "2 expected target-hours" in body
    assert "First detected:       2026-10-16T14:50:00Z" in body
    assert "http://localhost:8501" in body
    assert "Fetch failed after 3 attempts" in body  # reason
    assert "Next step:" in body and "--hour 2026-10-16T14:30:00Z" in body
    assert "- men black jeans: failed" in body and "- women handbag: failed" in body


def test_parser_error_alert_respects_threshold(tmp_path):
    keywords = ["men black jeans", "women handbag", "men hoodie", "women saree"]
    layout = fixture_text("layout_changed.html")

    def fn(keyword, page, n):
        if keyword in keywords[:3]:
            return resp(layout, keyword=keyword)
        return resp(fixture_text("small_page.html"), keyword=keyword) if page == 1 else resp(fixture_text("zero_results.html"), keyword=keyword, page=2)

    config = isolated_config(tmp_path, keywords)
    run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)
    db = _db(config)

    config.settings["alerts"]["parser_error_threshold"] = 4  # 3 bad targets: below the threshold
    assert "parser_errors" not in check_hour(db, config, HOUR, now=DUE, mailer=FakeMailer())["conditions"]

    config.settings["alerts"]["parser_error_threshold"] = 3
    mailer = FakeMailer()
    result = check_hour(db, config, HOUR, now=DUE, mailer=mailer)
    assert "parser_errors" in result["conditions"]
    assert "Parser/schema errors" in mailer.sent[0][1]
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product WHERE keyword IN ('men black jeans','women handbag','men hoodie')")[0]["n"] == 0


def test_missing_slots_and_completeness_alert_when_nothing_ran(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans", "women handbag"])
    mailer = FakeMailer()
    result = check_hour(_db(config), config, HOUR, now=DUE, mailer=mailer)
    assert result["conditions"] == ["missing_slots", "completeness"]
    subject, body = mailer.sent[0]
    assert subject.startswith("[AJIO VISIBILITY][CRITICAL] Missing data — 2026-10-16 14:30 UTC")
    assert "no run recorded for this hour" in body
    assert "grace period" in body


def test_not_due_before_grace_period_sends_nothing(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    mailer = FakeMailer()
    result = check_hour(_db(config), config, HOUR, now=datetime(2026, 10, 16, 14, 35, tzinfo=timezone.utc), mailer=mailer)
    assert result["alert_state"] == "not_due"
    assert mailer.sent == []


def _run_hour(config, hour, adapter=None):
    return run_pipeline(config, hour, trigger="backfill", adapter_override=adapter, sleeper=no_sleep)


def test_row_count_drop_against_rolling_baseline(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    generated = MockAdapter(config.fixtures_dir, generate=True)
    for hour in ("2026-10-16T08:30:00Z", "2026-10-16T09:30:00Z", "2026-10-16T10:30:00Z"):
        assert _run_hour(config, hour, generated)["rows_written_or_upserted"] == 35

    def small(keyword, page, n):
        return resp(fixture_text("small_page.html")) if page == 1 else resp(fixture_text("zero_results.html"), page=2)

    summary = _run_hour(config, "2026-10-16T11:30:00Z", ScriptedAdapter(small))
    assert summary["rows_written_or_upserted"] == 2
    mailer = FakeMailer()
    result = check_hour(_db(config), config, "2026-10-16T11:30:00Z", now=datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc), mailer=mailer)
    assert result["conditions"] == ["row_drop"]
    assert "wrote 2 rows; the rolling median of the last 3 comparable runs is 35" in mailer.sent[0][1]


def test_no_row_drop_alert_without_enough_baseline(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    generated = MockAdapter(config.fixtures_dir, generate=True)
    for hour in ("2026-10-16T08:30:00Z", "2026-10-16T09:30:00Z"):
        _run_hour(config, hour, generated)

    def small(keyword, page, n):
        return resp(fixture_text("small_page.html")) if page == 1 else resp(fixture_text("zero_results.html"), page=2)

    _run_hour(config, "2026-10-16T11:30:00Z", ScriptedAdapter(small))
    result = check_hour(_db(config), config, "2026-10-16T11:30:00Z", now=datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc), mailer=FakeMailer())
    assert result["conditions"] == []


def test_stale_data_alert_when_no_recent_success(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"], stale_sla_minutes=120)
    real_now = datetime.now(timezone.utc)
    hour = real_now.replace(minute=0, second=0, microsecond=0)
    assert run_pipeline(config, hour, sleeper=no_sleep)["status"] == "success"
    db = _db(config)
    fresh = check_hour(db, config, hour, now=real_now + timedelta(minutes=10), mailer=FakeMailer())
    assert "stale_data" not in fresh["conditions"]
    later = real_now + timedelta(hours=3)
    mailer = FakeMailer()
    stale = check_hour(db, config, later.replace(minute=0, second=0, microsecond=0), now=later, mailer=mailer)
    assert "stale_data" in stale["conditions"]
    assert any("Stale data" in body for _, body in mailer.sent)


def test_incident_dedup_cooldown_and_single_recovery(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans", "women handbag"])
    db = _db(config)
    mailer = FakeMailer()
    assert check_hour(db, config, HOUR, now=DUE, mailer=mailer)["alert_state"] == "sent"
    for minutes in (1, 2, 30):
        assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=minutes), mailer=mailer)["alert_state"] == "aggregated"
    assert len(mailer.sent) == 1
    assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=61), mailer=mailer)["alert_state"] == "reminder_sent"
    assert len(mailer.sent) == 2
    incident = db.query("SELECT * FROM alert_incident")
    assert len(incident) == 1 and incident[0]["send_count"] == 2

    run_pipeline(config, HOUR, trigger="backfill", sleeper=no_sleep)
    assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=70), mailer=mailer)["alert_state"] == "resolved"
    assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=71), mailer=mailer)["alert_state"] == "healthy"
    recoveries = [s for s in mailer.subjects if "[RECOVERED]" in s]
    assert len(recoveries) == 1 and len(mailer.sent) == 3
    resolved = db.query("SELECT * FROM alert_incident")[0]
    assert resolved["resolved_at"] is not None and resolved["recovery_sent_at"] is not None


def test_failed_email_delivery_keeps_state_and_retries(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    db = _db(config)
    broken = FakeMailer(ok=False)
    assert check_hour(db, config, HOUR, now=DUE, mailer=broken)["alert_state"] == "send_failed"
    incident = db.query("SELECT * FROM alert_incident")[0]
    assert incident["send_count"] == 0 and incident["last_sent_at"] is None
    assert "delivery failed" in incident["last_error"]
    assert db.query("SELECT COUNT(*) AS n FROM target_hour_status WHERE status='missing'")[0]["n"] == 1  # monitoring state kept

    working = FakeMailer()
    assert check_hour(db, config, HOUR, now=DUE + timedelta(minutes=5), mailer=working)["alert_state"] == "sent"
    assert db.query("SELECT send_count, last_error FROM alert_incident")[0] == {"send_count": 1, "last_error": None}
    assert len(working.sent) == 1
