from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import isolated_config


def test_full_50_keyword_mock_run_writes_raw_silver_and_status(tmp_path):
    config = isolated_config(tmp_path)
    result = run_pipeline(config, scheduled_hour="2026-10-16T14:30:00Z")
    db = Database(config.db_path, config.root)
    assert result["status"] == "success"
    assert result["expected_targets"] == result["completed_targets"] == 50
    assert result["status_counts"]["zero_result"] == 2
    assert result["status_counts"]["success"] == 48
    assert result["rows_written_or_upserted"] >= 100
    assert len(db.query("SELECT * FROM raw_snapshot WHERE run_id=?", (result["run_id"],))) >= 90
    assert len(db.query("SELECT * FROM target_hour_status WHERE scheduled_hour=?", (result["scheduled_hour"],))) == 50
    assert len(db.query("SELECT * FROM visibility_product WHERE run_id=?", (result["run_id"],))) == result["rows_written_or_upserted"]
    sample = db.query("SELECT * FROM visibility_product WHERE run_id=? LIMIT 1", (result["run_id"],))[0]
    assert sample["scheduled_hour"] == result["scheduled_hour"]
    assert sample["is_mock"] == 1
    assert sample["raw_payload_ref"].startswith("data/raw/")


def test_parser_failure_is_not_recorded_as_zero_result(tmp_path):
    from src.collectors.mock_adapter import MockAdapter

    config = isolated_config(tmp_path, ["men white sneakers"])
    adapter = MockAdapter(config.fixtures_dir, page_mapping={("men white sneakers", 1): "layout_changed.html"})
    result = run_pipeline(config, scheduled_hour="2026-10-16T14:30:00Z", adapter_override=adapter)
    db = Database(config.db_path, config.root)
    status = db.query("SELECT status,missing_reason FROM target_hour_status")
    assert result["status"] == "failed"
    assert status[0]["status"] == "parse_failed"
    assert "grid" in status[0]["missing_reason"].lower()
    assert db.query("SELECT * FROM visibility_product") == []


def test_rank_sequence_continues_across_pages(tmp_path):
    from src.collectors.mock_adapter import MockAdapter

    config = isolated_config(tmp_path, ["men white sneakers"])
    adapter = MockAdapter(
        config.fixtures_dir,
        page_mapping={
            ("men white sneakers", 1): "mixed_placements.html",
            ("men white sneakers", 2): "page2_results.html",
        },
    )
    result = run_pipeline(config, scheduled_hour="2026-10-16T14:30:00Z", adapter_override=adapter)
    db = Database(config.db_path, config.root)
    rows = db.query("SELECT absolute_rank,relative_rank,page_number,product_type FROM visibility_product ORDER BY absolute_rank")
    assert result["status"] == "success"
    assert [row["absolute_rank"] for row in rows] == [1, 2, 3, 4, 5]
    assert [row["relative_rank"] for row in rows] == [1, 1, 1, 2, 2]
    assert [row["page_number"] for row in rows] == [1, 1, 1, 2, 2]


def test_platform_code_is_the_search_surface(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    run_pipeline(config, scheduled_hour="2026-10-16T14:30:00Z")
    db = Database(config.db_path, config.root)
    codes = {(r["platform"], r["platform_code"]) for r in db.query("SELECT platform, platform_code FROM visibility_product")}
    assert codes == {("AJIO", "search")}
