from ajio_pipeline.parsing import parse_price, parse_count, product_key


def test_price_formats():
    assert parse_price("₹1,299") == "1299.00"
    assert parse_price("Rs. 1299.00") == "1299.00"
    assert parse_price(None) is None
    assert parse_price("") is None


def test_count_formats():
    assert parse_count("1.2K") == 1200
    assert parse_count("(1,234)") == 1234
    assert parse_count(None) is None


def test_product_key_ignores_tracking_and_title():
    a = "https://www.ajio.com/vastrado-men-slim-fit-kurta/p/703275794_white"
    b = a + "?utm_source=x&itm_source=search"
    assert product_key(a) == product_key(b) == "703275794_white"
    assert product_key("https://www.ajio.com/anything-else/p/703275794_white") == "703275794_white"
