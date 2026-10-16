"""Focused regression tests for assessment curveballs that must remain explicit."""
from datetime import datetime, timezone

from src.parsers.product_parser import ProductUnit
from src.pipeline.completeness import evaluate_completeness
from src.pipeline.validator import deduplicate_units
from src.storage.database import Database
from tests.helpers import isolated_config


def unit(product_type, product_id="sku-1", url="https://example.test/p/sku-1?track=a", campaign_id=None):
    return ProductUnit(
        product_id=product_id, product_url=url, product_name="Sample product", sp="1299.00",
        mrp="1999.00", rating=4.2, num_of_rating=1200, tag="", deal="",
        product_image_u="https://example.test/image.jpg", product_type=product_type,
        campaign_id=campaign_id,
    )


def test_same_product_sponsored_and_organic_are_distinct_but_tracking_duplicate_removed():
    placements = [
        unit("SP", url="https://example.test/p/sku-1?utm_source=ad", campaign_id="campaign-1"),
        unit("Organic", url="https://example.test/p/sku-1?utm_source=organic"),
        unit("Organic", url="https://example.test/p/sku-1?another=tracking"),
    ]
    kept, duplicate_count = deduplicate_units(placements)
    assert [p.product_type for p in kept] == ["SP", "Organic"]
    assert duplicate_count == 1


def test_hour_input_is_normalized_to_utc_hour_boundary():
    from src.pipeline.completeness import format_hour
    dt = datetime.fromisoformat("2026-10-16T10:59:58+05:30")
    assert format_hour(dt) == "2026-10-16T05:00:00Z"


def test_missing_slot_becomes_missing_after_grace_period(tmp_path):
    config = isolated_config(tmp_path, ["men white sneakers", "zxqvbn shirt"])
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    result = evaluate_completeness(
        db, config.platform, "2026-10-16T14:00:00Z", grace_period_minutes=15,
        threshold=0.98, now=datetime(2026, 10, 16, 14, 20, tzinfo=timezone.utc),
    )
    assert result["due"] is True
    assert result["completed_targets"] == 0
    assert result["status_counts"]["missing"] == 2
    assert result["meets_threshold"] is False
