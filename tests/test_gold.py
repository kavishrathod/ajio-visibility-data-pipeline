"""Gold layer: SQL views over Silver and the status ledger."""
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOUR = "2026-10-16T14:30:00Z"  # 20:00 IST


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


def _run(config, pages):
    """pages: {keyword: (page1_body, status)}; page 2 is always a valid zero-result page."""
    def fn(keyword, page, n):
        body, status = pages[keyword]
        if page == 1:
            return resp(body, status)
        return resp(fixture_text("zero_results.html"), page=2)
    return run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)


def test_keyword_hour_view_counts_units_prices_and_zero_results(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans", "zxqvbn shirt"])
    _run(config, {
        "men black jeans": (fixture_text("mixed_placements.html"), 200),  # SB + SP + Organic
        "zxqvbn shirt": (fixture_text("zero_results.html"), 200),
    })
    rows = {r["keyword"]: r for r in _db(config).query("SELECT * FROM gold_keyword_hour")}
    mixed = rows["men black jeans"]
    assert (mixed["status"], mixed["total_units"]) == ("success", 3)
    assert (mixed["organic_units"], mixed["sp_units"], mixed["sb_units"]) == (1, 1, 1)
    assert mixed["paid_share_pct"] == 66.7
    assert mixed["distinct_products"] == 2          # the SB banner has no product id
    assert (mixed["min_sp"], mixed["avg_sp"], mixed["max_sp"]) == (1299, 1399.0, 1499)
    assert mixed["avg_rating"] == 4.05
    zero = rows["zxqvbn shirt"]
    # A genuine zero result is a row with status zero_result and no units, not a missing row.
    assert (zero["status"], zero["total_units"], zero["organic_units"]) == ("zero_result", 0, 0)
    assert zero["paid_share_pct"] is None and zero["avg_sp"] is None


def test_product_placement_view_compares_organic_rank_with_sponsored_rank(tmp_path):
    config = isolated_config(tmp_path, ["men white sneakers"])
    _run(config, {"men white sneakers": (fixture_text("jsonld_identity.html"), 200)})
    rows = {r["product_id"]: r for r in _db(config).query("SELECT * FROM gold_product_placement")}
    both = rows["920000001"]   # SP at SP-rank 1 and Organic at organic-rank 2 on the same page (I-6)
    assert (both["best_sp_rank"], both["best_organic_rank"]) == (1, 2)
    assert (both["sp_placements"], both["organic_placements"]) == (1, 1)
    organic_only = rows["920000002"]
    assert (organic_only["best_organic_rank"], organic_only["best_sp_rank"]) == (1, None)
    assert organic_only["sp_placements"] == 0


def test_hour_summary_view_matches_the_status_ledger(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans", "zxqvbn shirt", "women handbag"])
    _run(config, {
        "men black jeans": (fixture_text("mixed_placements.html"), 200),
        "zxqvbn shirt": (fixture_text("zero_results.html"), 200),
        "women handbag": ("Forbidden", 403),
    })
    row = _db(config).query("SELECT * FROM gold_hour_summary")[0]
    assert row["scheduled_hour"] == HOUR
    assert (row["targets"], row["complete"], row["zero_result"], row["problem"], row["missing"]) == (3, 2, 1, 1, 0)
    assert row["rows"] == 3
    assert row["completeness_pct"] == 66.7


def test_gold_views_do_not_double_count_after_a_rerun(tmp_path):
    config = isolated_config(tmp_path, ["men black jeans"])
    pages = {"men black jeans": (fixture_text("mixed_placements.html"), 200)}
    _run(config, pages)
    _run(config, pages)
    db = _db(config)
    assert db.query("SELECT total_units FROM gold_keyword_hour")[0]["total_units"] == 3
    assert db.query("SELECT rows FROM gold_hour_summary")[0]["rows"] == 3
