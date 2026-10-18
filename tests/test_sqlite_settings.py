"""SQLite settings (test-only fast mode, durable defaults) and upgrade of older local databases."""
import sqlite3

import pytest

from src.storage.database import FAST_SQLITE_ENV, Database


def _pragma(db, name):
    with db.connect() as conn:
        return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_production_keeps_sqlites_durable_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv(FAST_SQLITE_ENV, raising=False)
    db = Database(tmp_path / "d.db", tmp_path)
    assert (_pragma(db, "journal_mode"), _pragma(db, "synchronous")) == ("delete", 2)      # rollback journal on disk, FULL sync
    monkeypatch.setenv(FAST_SQLITE_ENV, "0")
    assert (_pragma(db, "journal_mode"), _pragma(db, "synchronous")) == ("delete", 2)      # only "1" turns the fast mode on


def test_the_test_suite_runs_in_fast_mode(tmp_path, monkeypatch):
    monkeypatch.setenv(FAST_SQLITE_ENV, "1")
    db = Database(tmp_path / "d.db", tmp_path)
    assert (_pragma(db, "journal_mode"), _pragma(db, "synchronous")) == ("memory", 0)
    assert foreign_keys_on(db)


def foreign_keys_on(db):
    return _pragma(db, "foreign_keys") == 1



from pathlib import Path

def _old_database(tmp_path):
    """A database as created by an earlier version: no brand/duplicate columns, image column named product_image_u."""
    project_root = Path(__file__).resolve().parents[1]
    db = Database(tmp_path / "old.db", project_root)
    db.initialize()
    with db.connect() as conn:
        for view in ("gold_brand_placement", "gold_brand_coverage", "gold_hour_summary", "gold_keyword_hour",
                     "gold_product_placement", "gold_quarantine_summary"):
            conn.execute(f"DROP VIEW IF EXISTS {view}")
        conn.execute("ALTER TABLE visibility_product DROP COLUMN brand")
        conn.execute("ALTER TABLE visibility_product DROP COLUMN brand_key")
        conn.execute("ALTER TABLE target_hour_status DROP COLUMN duplicate_count")
        conn.execute("ALTER TABLE visibility_product RENAME COLUMN product_image_url TO product_image_u")
    return db



@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 35), reason="the test removes columns, which needs SQLite 3.35+")
def test_an_older_database_is_upgraded_in_place(tmp_path):
    db = _old_database(tmp_path)
    columns = lambda table: {r[1] for r in sqlite3.connect(db.path).execute(f"PRAGMA table_info({table})")}
    assert "brand" not in columns("visibility_product") and "product_image_u" in columns("visibility_product")
    db.initialize()
    assert {"brand", "brand_key", "product_image_url"} <= columns("visibility_product")
    assert "product_image_u" not in columns("visibility_product")
    assert "duplicate_count" in columns("target_hour_status")
    for view in ("gold_brand_placement", "gold_brand_coverage", "gold_hour_summary"):
        db.query(f"SELECT * FROM {view} LIMIT 1")                           # the views work on the upgraded tables
    db.initialize()                                                         # and upgrading twice is harmless
