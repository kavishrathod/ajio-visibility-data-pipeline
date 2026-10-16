from pathlib import Path

from src.parsers.product_parser import parse_count, parse_price, parse_products, parse_rating, product_key

FIXTURES = Path(__file__).parent / "fixtures"


def body(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_normal_page_parses_products_and_money():
    result = parse_products(body("normal_results.html"))
    assert result.status == "ok"
    assert len(result.units) == 3
    assert result.units[0].sp == "799.00"
    assert result.units[0].mrp == "1499.00"
    assert result.units[0].num_of_rating == 1200
    assert result.units[0].product_type == "Organic"


def test_valid_zero_results_is_not_a_parse_failure():
    result = parse_products(body("zero_results.html"))
    assert result.status == "zero_result"
    assert result.units == []


def test_layout_change_is_not_mistaken_for_zero_results():
    result = parse_products(body("layout_changed.html"))
    assert result.status == "parse_failed"
    assert "grid" in result.reason.lower()


def test_mixed_placements_keep_paid_and_organic_separate():
    result = parse_products(body("mixed_placements.html"))
    assert result.status == "ok"
    assert [unit.product_type for unit in result.units] == ["SB", "SP", "Organic"]
    assert result.units[0].campaign_id == "MOCK-CMP-001"
    assert result.units[0].product_id is None


def test_messy_values_are_null_not_zero_and_duplicates_are_visible_to_validator():
    result = parse_products(body("messy_values.html"))
    assert result.status == "ok"
    assert result.units[0].sp is None  # Ambiguous range, not guessed
    assert result.units[0].mrp is None
    assert result.units[0].num_of_rating == 2500
    assert result.units[1].sp is None
    assert result.units[1].rating is None
    assert len(result.units) == 4


def test_price_count_rating_and_product_key_helpers():
    assert parse_price("₹1,299") == "1299.00"
    assert parse_price("Rs. 1299.00") == "1299.00"
    assert parse_price("₹899 – ₹1,299") is None
    assert parse_price(None) is None
    assert parse_count("1.2K") == 1200
    assert parse_count("2.5M") == 2_500_000
    assert parse_count("(1,234)") == 1234
    assert parse_count("—") is None
    assert parse_rating("4.4 out of 5") == 4.4
    assert parse_rating("not-rated") is None
    url = "https://www.ajio.com/sample/p/703275794_white?utm_source=x"
    assert product_key(url) == "703275794_white"
    assert product_key("https://example.invalid/no-product-key") is None


def test_blocked_and_challenge_pages_never_parse_as_zero_results():
    assert parse_products(body("zero_results.html"), http_status=403).status == "blocked"
    assert parse_products("<html><body>Verify you are human</body></html>").status == "blocked"
