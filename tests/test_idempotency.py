from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import isolated_config


def test_same_hour_rerun_upserts_instead_of_duplicate_rows(tmp_path):
    config = isolated_config(tmp_path, ["men white sneakers"])
    hour = "2026-10-16T14:00:00Z"
    first = run_pipeline(config, scheduled_hour=hour, trigger="manual")
    db = Database(config.db_path, config.root)
    first_rows = db.query("SELECT * FROM visibility_product WHERE scheduled_hour=?", (hour,))
    assert first["status"] == "success"
    assert len(first_rows) == 3

    second = run_pipeline(config, scheduled_hour=hour, trigger="backfill")
    second_rows = db.query("SELECT * FROM visibility_product WHERE scheduled_hour=?", (hour,))
    assert second["status"] == "success"
    assert len(second_rows) == 3
    assert len({row["absolute_rank"] for row in second_rows}) == 3
    assert len(db.query("SELECT * FROM scrape_run WHERE scheduled_hour=?", (hour,))) == 2
    assert len(db.query("SELECT * FROM raw_snapshot WHERE run_id=?", (second["run_id"],))) == 2
