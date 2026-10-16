from src.storage.database import Database
from tests.helpers import isolated_config


def test_database_creates_all_required_tables_and_targets(tmp_path):
    config = isolated_config(tmp_path, ["men white sneakers", "zxqvbn shirt"])
    db = Database(config.db_path, config.root)
    db.initialize()
    targets = db.ensure_targets(config.targets)
    assert len(targets) == 2
    names = {row["name"] for row in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"scrape_run", "scrape_target", "visibility_product", "target_hour_status", "alert_incident", "raw_snapshot", "pipeline_lock"} <= names


def test_global_lock_rejects_overlapping_runs(tmp_path):
    import pytest

    config = isolated_config(tmp_path, ["men white sneakers"])
    db = Database(config.db_path, config.root)
    db.initialize()
    db.acquire_lock("pipeline:AJIO", "run-1")
    with pytest.raises(RuntimeError, match="overlapping execution"):
        db.acquire_lock("pipeline:AJIO", "run-2")
    db.release_lock("pipeline:AJIO", "run-1")
    db.acquire_lock("pipeline:AJIO", "run-3")
    db.release_lock("pipeline:AJIO", "run-3")
