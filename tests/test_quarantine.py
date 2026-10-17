"""Quarantine layer: rejected cards, units and pages are kept with a reason instead of silently dropped."""
import json
import sqlite3

from src.collectors.mock_adapter import MockAdapter
from src.parsers.product_parser import ProductUnit
from src.pipeline.orchestrator import reload_raw, run_pipeline
from src.pipeline.validator import validate_entries
from src.storage.database import Database
from tests.helpers import ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOUR = "2026-10-16T14:30:00Z"  # 20:00 IST


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


def _one_page(body_name, status=200):
    """Page 1 serves the named fixture; page 2 is a valid zero-result page."""
    def fn(keyword, page, n):
        return resp(fixture_text(body_name), status) if page == 1 else resp(fixture_text("zero_results.html"), page=2)
    return ScriptedAdapter(fn)


def _quarantine(db):
    return db.query("SELECT * FROM quarantine_record ORDER BY page_number, record_type, record_index, reason_code")


def test_rejected_cards_and_duplicates_are_quarantined_with_reason_and_payload(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    summary = run_pipeline(config, HOUR, adapter_override=_one_page("quarantine_cards.html"), sleeper=no_sleep)
    db = _db(config)
    rows = _quarantine(db)
    assert [(r["record_type"], r["record_index"], r["stage"], r["reason_code"]) for r in rows] == [
        ("card", 2, "parse", "card_missing_name"),
        ("card", 3, "parse", "card_missing_identity"),
        ("unit", 2, "dedupe", "duplicate_placement"),   # 2nd entry that the parser accepted: card 4
    ]
    missing_name, missing_identity, duplicate = rows
    assert json.loads(missing_name["payload_json"])["attributes"]["data-product-id"] == "711"
    assert json.loads(missing_identity["payload_json"])["attributes"]["data-name"] == "Mock Anonymous Item"
    assert json.loads(duplicate["payload_json"])["product_id"] == "710"
    assert duplicate["reason_detail"] == "same placement already kept from page 1; repeated on page 1"
    # Each row points at the exact raw page it came from, and that file exists.
    for row in rows:
        assert row["raw_payload_ref"].endswith("men_black_jeans__p1.html")
        assert (config.root / row["raw_payload_ref"]).is_file()
        assert (row["run_id"], row["scheduled_hour"], row["keyword"], row["is_mock"]) == (summary["run_id"], HOUR, "men black jeans", 1)
    # Quarantine changes nothing about the outcome: the valid placements load and the slot is a success.
    assert summary["status"] == "success"
    silver = db.query("SELECT product_id, product_type, absolute_rank FROM visibility_product ORDER BY absolute_rank")
    assert [(r["product_id"], r["product_type"], r["absolute_rank"]) for r in silver] == [("710", "Organic", 1), ("712", "SP", 2)]
    assert summary["quarantined_records"] == 3
    assert summary["quarantine_reasons"] == {"card_missing_identity": 1, "card_missing_name": 1, "duplicate_placement": 1}


def test_cross_page_duplicate_is_quarantined_and_names_the_page_that_was_kept(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    adapter = MockAdapter(config.root / "tests" / "fixtures", page_mapping={
        ("men black jeans", 1): "pagination_drift_page1.html", ("men black jeans", 2): "pagination_drift_page2.html"})
    run_pipeline(config, HOUR, adapter_override=adapter, sleeper=no_sleep)
    rows = _quarantine(_db(config))
    assert len(rows) == 1
    row = rows[0]
    assert (row["reason_code"], row["stage"], row["page_number"]) == ("cross_page_duplicate", "dedupe", 2)
    assert row["reason_detail"] == "same placement already kept from page 1; repeated on page 2"
    assert json.loads(row["payload_json"])["product_id"] == "333"


def test_unparseable_and_blocked_pages_are_quarantined_but_a_zero_result_is_not(tmp_path):
    config = isolated_config(tmp_path, ["k layout", "k blocked", "k challenge", "k zero"])
    def fn(keyword, page, n):
        return {
            "k layout": resp(fixture_text("layout_changed.html")),
            "k blocked": resp("Forbidden", 403),
            "k challenge": resp(fixture_text("bot_challenge.html")),
            "k zero": resp(fixture_text("zero_results.html")),
        }[keyword]
    summary = run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)
    db = _db(config)
    by_keyword = {r["keyword"]: r for r in _quarantine(db)}
    assert set(by_keyword) == {"k layout", "k blocked", "k challenge"}      # k zero is healthy: nothing to quarantine
    assert (by_keyword["k layout"]["record_type"], by_keyword["k layout"]["reason_code"]) == ("page", "page_parse_failed")
    assert by_keyword["k layout"]["reason_detail"] == "Expected product grid container is missing"
    assert by_keyword["k blocked"]["reason_code"] == "page_blocked"
    assert json.loads(by_keyword["k blocked"]["payload_json"]) == {"http_status": 403}
    assert by_keyword["k challenge"]["reason_code"] == "page_blocked"
    assert summary["quarantined_records"] == 3


def test_rerun_keeps_history_but_the_summary_counts_the_latest_attempt_only(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    run_pipeline(config, HOUR, adapter_override=_one_page("quarantine_cards.html"), sleeper=no_sleep)
    run_pipeline(config, HOUR, adapter_override=_one_page("quarantine_cards.html"), sleeper=no_sleep)
    db = _db(config)
    assert db.query("SELECT COUNT(*) AS n FROM quarantine_record")[0]["n"] == 6                  # two attempts kept as history
    assert db.query("SELECT COUNT(DISTINCT run_id) AS n FROM quarantine_record")[0]["n"] == 2
    summary = {r["reason_code"]: r["records"] for r in db.query("SELECT * FROM gold_quarantine_summary")}
    assert summary == {"card_missing_name": 1, "card_missing_identity": 1, "duplicate_placement": 1}   # not doubled


def test_saving_the_same_rows_twice_in_one_run_is_idempotent(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    summary = run_pipeline(config, HOUR, adapter_override=_one_page("quarantine_cards.html"), sleeper=no_sleep)
    db = _db(config)
    existing = db.query("SELECT * FROM quarantine_record")
    db.save_quarantine([{k: v for k, v in row.items() if k != "quarantine_id"} for row in existing])
    assert db.query("SELECT COUNT(*) AS n FROM quarantine_record")[0]["n"] == 3
    assert {r["run_id"] for r in existing} == {summary["run_id"]}


def test_reload_raw_rebuilds_quarantine_without_refetching(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    run_pipeline(config, HOUR, adapter_override=_one_page("quarantine_cards.html"), sleeper=no_sleep)
    db = _db(config)
    db.execute("DELETE FROM quarantine_record")                       # as if the rows were lost
    replay = reload_raw(config, HOUR)
    assert replay["trigger"] == "reload" and replay["quarantined_records"] == 3
    assert {r["reason_code"] for r in _quarantine(db)} == {"card_missing_name", "card_missing_identity", "duplicate_placement"}


def test_a_failed_quarantine_write_never_changes_the_target_status(tmp_path, monkeypatch):
    config = isolated_config(tmp_path, ["men black jeans"])
    def boom(self, records):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(Database, "save_quarantine", boom)
    summary = run_pipeline(config, HOUR, adapter_override=_one_page("quarantine_cards.html"), sleeper=no_sleep)
    db = _db(config)
    assert db.query("SELECT status FROM target_hour_status")[0]["status"] == "success"
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product")[0]["n"] == 2
    assert summary["db_errors"][0].startswith("quarantine: OperationalError")
    assert summary["quarantined_records"] == 0


def test_validate_entries_reports_every_rule_with_a_machine_readable_code():
    def entry(unit, page=1):
        return {"unit": unit, "page_number": page, "raw_payload_ref": "raw.html", "is_mock": 1}
    good = ProductUnit(product_type="Organic", product_name="A", product_id="1")
    bad_rating = ProductUnit(product_type="Organic", product_name="B", product_id="2", rating=7.5)
    bad_count = ProductUnit(product_type="Organic", product_name="C", product_id="3", num_of_rating=-4)
    bad_type = ProductUnit(product_type="Weird", product_name="D", product_id="4")
    no_name = ProductUnit(product_type="Organic", product_name="  ", product_id="5")
    repeat = ProductUnit(product_type="Organic", product_name="A", product_id="1")
    accepted, rejected = validate_entries([entry(u) for u in (good, bad_rating, bad_count, bad_type, no_name)] + [entry(repeat, page=2)])
    assert [e["unit"].product_id for e in accepted] == ["1"]
    assert [(r["stage"], r["reason_code"]) for r in rejected] == [
        ("validate", "rating_out_of_range"), ("validate", "negative_rating_count"),
        ("validate", "invalid_product_type"), ("validate", "missing_product_name"),
        ("dedupe", "cross_page_duplicate"),
    ]
