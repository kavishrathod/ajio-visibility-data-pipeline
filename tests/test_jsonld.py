"""JSON-LD ItemList layer (observed structure) joined to the simulated product grid."""
from pathlib import Path

from src.collectors.synthetic import render_page
from src.parsers.product_parser import parse_products

FIXTURES = Path(__file__).parent / "fixtures"


def body(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_identity_comes_from_json_ld_when_cards_do_not_carry_it():
    result = parse_products(body("jsonld_identity.html"))
    assert result.status == "ok"
    assert result.total_items == 1200
    assert [u.product_type for u in result.units] == ["SB", "SP", "Organic", "Organic"]
    sb, sp, org_b, org_a = result.units
    # Banner is not in the ItemList: it keeps its own name and has no product URL.
    assert (sb.product_name, sb.product_url, sb.campaign_id) == ("Mock Brand Banner", None, "MOCK-CMP-777")
    # Products: name, url and image are filled from JSON-LD, money comes from the grid.
    assert (sp.product_name, sp.product_image_url) == ("Mock Brand Sneaker A", "https://example.invalid/img/920000001.jpg")
    assert sp.product_url == "https://www.ajio.com/mock-brand-sneaker-a/p/920000001_white?itm_source=search"
    assert (sp.sp, sp.mrp, sp.num_of_rating, sp.campaign_id) == ("1299.00", "2599.00", 1200, "MOCK-CMP-778")
    assert (org_b.product_name, org_b.sp, org_b.mrp, org_b.num_of_rating) == ("Mock Brand Sneaker B", "1499.00", None, 1234)
    # Same product as SP and Organic stays two units, linked to the 1st and 3rd ItemList entries.
    assert (org_a.product_name, org_a.product_id) == ("Mock Brand Sneaker A", "920000001")
    assert result.warnings == []


def test_json_ld_does_not_rescue_a_page_whose_grid_is_missing():
    result = parse_products(body("layout_changed_jsonld_present.html"))
    assert result.status == "parse_failed"
    assert result.units == []
    assert "grid container is missing" in result.reason


def test_json_ld_and_grid_disagreement_is_warned_and_not_trusted():
    result = parse_products(body("jsonld_mismatch.html"))
    assert result.status == "ok"
    # Card 1 matches entry 1; card 2 conflicts with entry 2 and card 3 has no entry: both skipped (no name).
    assert [u.product_id for u in result.units] == ["920000001"]
    joined = " | ".join(result.warnings)
    assert "JSON-LD lists 2 items but the grid has 3 non-banner cards" in joined
    assert "Card 2: JSON-LD entry 2 has product 999999999_black, grid says 920000002" in joined
    assert "Card 2 skipped: product name missing" in joined and "Card 3 skipped: product name missing" in joined


def test_malformed_json_ld_is_ignored_with_a_warning():
    html = body("jsonld_identity.html").replace('"numberOfItems":"1200",', '"numberOfItems":"1200"  BROKEN')
    result = parse_products(html)
    assert result.total_items is None
    assert any("not valid JSON" in w for w in result.warnings)
    # Cards no longer have names, so the product cards are skipped rather than guessed.
    assert [u.product_type for u in result.units] == ["SB"]


def test_json_ld_text_never_triggers_challenge_detection():
    html = body("jsonld_identity.html").replace("Mock Brand Sneaker B", "Access Denied Edition Sneaker B")
    assert parse_products(html).status == "ok"


def test_generated_pages_publish_identity_only_in_json_ld():
    page = render_page("men white sneakers", 1, "2026-10-16T04:30:00Z")
    assert page.count('type="application/ld+json"') == 1
    # Product cards carry no url attribute; only the JSON-LD block does.
    assert "data-url=" not in page
    result = parse_products(page)
    assert result.status == "ok" and result.total_items == 34
    products = [u for u in result.units if u.product_type != "SB"]
    assert products and all(u.product_name and u.product_url and u.product_image_url for u in products)
