"""Duplicate-spike detection (Task E): measure repeated placements per hour and alert on an anomalous rise."""
from datetime import datetime, timezone

from src.collectors.mock_adapter import MockAdapter
from src.monitoring.alerts import check_hour
from src.monitoring.duplicates import baseline_rates, detect_duplicate_spike, slot_duplicate_stats
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import FakeMailer, ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOURS = ["2026-10-16T10:30:00Z", "2026-10-16T11:30:00Z", "2026-10-16T12:30:00Z", "2026-10-16T13:30:00Z", "2026-10-16T14:30:00Z"]
KEYWORDS = [f"men shirt {n}" for n in range(1, 13)]  # 12 targets


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


def _now(hour: str) -> datetime:
    return datetime.fromisoformat(hour.replace("Z", "+00:00")).replace(minute=50)  # after the grace period


def _cards(unique: int, repeats: int) -> str:
    """A generated page: ``unique`` distinct organic products followed by ``repeats`` repeats of the first ones."""
    def card(n):
        return (f'<article class="product-card" data-kind="ORGANIC" data-name="Mock P{n}" data-product-id="{900 + n}" '
                f'data-url="https://www.ajio.com/mock-p{n}/p/{900 + n}_white" data-price="₹{500 + n}"></article>')
    body = "".join(card(n) for n in list(range(1, unique + 1)) + list(range(1, repeats + 1)))
    return f'<html><body><section data-testid="product-grid">{body}</section></body></html>'


def _run(config, hour, page_one):
    def fn(keyword, page, n):
        return resp(page_one, keyword=keyword) if page == 1 else resp(fixture_text("zero_results.html"), keyword=keyword, page=2)
    return run_pipeline(config, hour, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)


def test_a_duplicate_spike_is_detected_and_alerted_with_the_evidence(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS[:5])
    for hour in HOURS[:3]:
        _run(config, hour, fixture_text("small_page.html"))                    # three clean hours: no duplicates
    spike_hour = HOURS[3]
    _run(config, spike_hour, fixture_text("duplicate_spike.html"))             # every target repeats 3 of 9 placements
    db = _db(config)

    stats = slot_duplicate_stats(db, "AJIO", spike_hour)
    assert (stats["duplicates"], stats["kept"], stats["targets"]) == (15, 30, 5)
    assert round(stats["rate"], 4) == 0.3333
    assert [a["duplicates"] for a in stats["affected"]] == [3, 3, 3, 3, 3]

    mailer = FakeMailer()
    result = check_hour(db, config, spike_hour, now=_now(spike_hour), mailer=mailer)
    assert result["conditions"] == ["duplicate_spike"] and result["alert_state"] == "sent"
    subject, body = mailer.sent[0]
    assert subject == "[AJIO VISIBILITY][WARNING] Duplicate spike — 2026-10-16 13:30 UTC (2026-10-16 19:00 IST)"
    assert "15 repeated placements were dropped across 5 target(s): 33.3% of 45 units seen" in body
    assert "spike threshold of 2.0% (and at least 10 duplicates)" in body
    assert "- men shirt 1: success — 3 duplicate placement(s) dropped" in body
    assert "Quarantine tab" in body

    # The same repeated placements are also kept as evidence in quarantine.
    quarantined = db.query("SELECT reason_code, COUNT(*) AS n FROM gold_quarantine_summary WHERE scheduled_hour=? GROUP BY reason_code", (spike_hour,))
    assert {r["reason_code"]: r["n"] for r in quarantined} == {"duplicate_placement": 1}
    assert db.query("SELECT records FROM gold_quarantine_summary WHERE scheduled_hour=?", (spike_hour,))[0]["records"] == 15

    hour_row = db.query("SELECT duplicates, duplicate_rate_pct FROM gold_hour_summary WHERE scheduled_hour=?", (spike_hour,))[0]
    assert (hour_row["duplicates"], hour_row["duplicate_rate_pct"]) == (15, 33.33)


def test_a_normal_mock_hour_is_not_a_spike(tmp_path):
    config = isolated_config(tmp_path)  # the 50 configured keywords
    adapter = MockAdapter(config.fixtures_dir, mapping=config.settings["mock_fixtures"], generate=True)
    run_pipeline(config, HOURS[0], adapter_override=adapter, sleeper=no_sleep)
    db = _db(config)
    stats = slot_duplicate_stats(db, "AJIO", HOURS[0])
    assert (stats["duplicates"], stats["targets"], stats["measured_targets"]) == (1, 50, 50)   # the one fixture duplicate
    assert detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[0]) is None
    assert check_hour(db, config, HOURS[0], now=_now(HOURS[0]), mailer=FakeMailer())["conditions"] == []


def test_a_few_duplicates_never_alert_however_high_their_share(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS[:1])
    _run(config, HOURS[0], fixture_text("duplicate_spike.html"))                # 3 duplicates = 33% of units, but only 3
    db = _db(config)
    stats = slot_duplicate_stats(db, "AJIO", HOURS[0])
    assert (stats["duplicates"], round(stats["rate"], 2)) == (3, 0.33)
    assert detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[0]) is None   # below the 10-duplicate minimum


def test_a_rise_must_also_exceed_the_rolling_baseline(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS)
    for hour in HOURS[:3]:
        _run(config, hour, _cards(unique=24, repeats=1))                        # 12 duplicates of 300 units = 4% every hour
    db = _db(config)
    assert [round(r, 2) for r in baseline_rates(db, "AJIO", HOURS[3], 12, 6)] == [0.04, 0.04, 0.04]

    _run(config, HOURS[3], _cards(unique=9, repeats=1))                         # 12 of 120 = 10%: over 2% but under 5 x 4%
    assert detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[3]) is None

    _run(config, HOURS[4], _cards(unique=6, repeats=3))                         # 36 of 108 = 33%: over 5 x the 4% median
    spike = detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[4])
    assert spike is not None
    assert (spike["duplicates"], spike["kept"], round(spike["rate"], 4)) == (36, 72, 0.3333)
    assert round(spike["baseline_rate"], 2) == 0.04 and spike["baseline_hours"] == 4
    assert round(spike["threshold_rate"], 2) == 0.2
    mailer = FakeMailer()
    check_hour(db, config, HOURS[4], now=_now(HOURS[4]), mailer=mailer)
    assert "20.0% (5x the rolling median 4.00% of the previous 4 complete hours)" in mailer.sent[0][1]


def test_without_three_baseline_hours_the_fixed_thresholds_decide(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS[:5])
    _run(config, HOURS[0], fixture_text("small_page.html"))
    _run(config, HOURS[1], fixture_text("duplicate_spike.html"))                # only one earlier hour exists
    db = _db(config)
    spike = detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[1])
    assert spike is not None and spike["baseline_rate"] is None and spike["baseline_hours"] == 1
    assert round(spike["threshold_rate"], 2) == 0.02


def test_the_spike_resolves_when_the_hour_is_rerun_clean_and_one_recovery_is_sent(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS[:5])
    for hour in HOURS[:3]:
        _run(config, hour, fixture_text("small_page.html"))
    spike_hour = HOURS[3]
    _run(config, spike_hour, fixture_text("duplicate_spike.html"))
    db = _db(config)
    mailer = FakeMailer()
    assert check_hour(db, config, spike_hour, now=_now(spike_hour), mailer=mailer)["alert_state"] == "sent"
    assert check_hour(db, config, spike_hour, now=_now(spike_hour), mailer=mailer)["alert_state"] == "aggregated"   # no repeat email
    _run(config, spike_hour, fixture_text("small_page.html"))                   # rerun without repeated placements
    result = check_hour(db, config, spike_hour, now=_now(spike_hour), mailer=mailer)
    assert (result["conditions"], result["alert_state"]) == ([], "resolved")
    assert mailer.subjects == [
        "[AJIO VISIBILITY][WARNING] Duplicate spike — 2026-10-16 13:30 UTC (2026-10-16 19:00 IST)",
        "[AJIO VISIBILITY][RECOVERED] Duplicate spike — 2026-10-16 13:30 UTC (2026-10-16 19:00 IST)",
    ]
    assert slot_duplicate_stats(db, "AJIO", spike_hour)["duplicates"] == 0


def test_an_unfinished_or_unmeasured_hour_is_never_reported_as_a_spike(tmp_path):
    config = isolated_config(tmp_path, KEYWORDS[:5])
    _run(config, HOURS[0], fixture_text("duplicate_spike.html"))
    db = _db(config)
    assert detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[0]) is not None
    db.execute("UPDATE target_hour_status SET status='running' WHERE target_id=(SELECT MIN(target_id) FROM scrape_target)")
    assert detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[0]) is None      # still running: do not guess
    db.execute("UPDATE target_hour_status SET status='success', duplicate_count=NULL WHERE target_id=(SELECT MIN(target_id) FROM scrape_target)")
    assert detect_duplicate_spike(db, config.settings["alerts"], "AJIO", HOURS[0]) is None      # one target not measured
