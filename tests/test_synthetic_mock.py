"""The seeded generator behind the mock adapter: deterministic, structured like the brief's worked example, varied across hours."""
from src.collectors.synthetic import ORGANIC_COUNT, PAGE_SIZE, build_listing, render_page
from src.parsers.product_parser import parse_products
from src.pipeline.ranking import RankState, assign_ranks

H1, H2 = "2026-10-16T05:30:00Z", "2026-10-16T06:30:00Z"


def _all_units(keyword, slot):
    units, page = [], 1
    while True:
        parsed = parse_products(render_page(keyword, page, slot))
        if parsed.status != "ok":
            return units, page
        units += parsed.units
        page += 1


def test_same_keyword_and_hour_produce_identical_html():
    assert render_page("men white sneakers", 1, H1) == render_page("men white sneakers", 1, H1)


def test_pages_are_labelled_synthetic_and_page_three_is_a_valid_empty_page():
    assert "SYNTHETIC MOCK FIXTURE" in render_page("women saree", 1, H1)
    assert parse_products(render_page("women saree", 3, H1)).status == "zero_result"


def test_listing_matches_the_worked_example_ranks():
    units, _ = _all_units("women saree", H1)
    types = [u.product_type for u in units]
    assert types[:6] == ["SB", "SP", "Organic", "Organic", "SP", "Organic"]  # the brief's worked example
    assert len(units) == 35 and types.count("Organic") == ORGANIC_COUNT and types.count("SP") == 4 and types.count("SB") == 1
    ranks, _ = assign_ranks(types)
    assert ranks[:6] == [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)]
    assert ranks[PAGE_SIZE] == (21, 17)  # page 1 held 16 organic units, so page 2 continues at organic #17


def test_sponsored_and_banner_units_carry_campaign_ids_and_organic_ones_do_not():
    units, _ = _all_units("women saree", H1)
    assert all(u.campaign_id for u in units if u.product_type in {"SB", "SP"})
    assert all(u.campaign_id is None for u in units if u.product_type == "Organic")
    banner = units[0]
    assert banner.sp is None and banner.mrp is None and banner.product_id is None  # banner: null price, still parses


def test_same_product_appears_as_sp_and_organic_with_different_urls():
    units, _ = _all_units("women saree", H1)
    by_id = {}
    for u in units:
        by_id.setdefault(u.product_id, set()).add(u.product_type)
    assert any(types == {"SP", "Organic"} for types in by_id.values())


def test_no_organic_product_repeats_across_pages():
    units, _ = _all_units("women saree", H1)
    organic_ids = [u.product_id for u in units if u.product_type == "Organic"]
    assert len(organic_ids) == len(set(organic_ids))


def test_ranks_and_prices_move_between_hours_but_the_catalogue_is_stable():
    a = [u for u in build_listing("men hoodie", H1) if u.kind == "ORGANIC"]
    b = [u for u in build_listing("men hoodie", H2) if u.kind == "ORGANIC"]
    assert sorted(x.product_id for x in a) == sorted(x.product_id for x in b)   # same products
    assert [x.product_id for x in a] != [x.product_id for x in b]               # different order
    price_changes = sum(1 for x in a for y in b if x.product_id == y.product_id and x.price != y.price)
    assert price_changes > 0


def test_different_keywords_get_different_catalogues():
    a = {u.product_id for u in build_listing("men hoodie", H1) if u.product_id}
    b = {u.product_id for u in build_listing("women handbag", H1) if u.product_id}
    assert a != b and len(a & b) == 0


def test_messy_price_and_count_formats_are_exercised_and_parse_to_exact_decimals():
    units, _ = _all_units("men hoodie", H1)
    for u in units:
        if u.sp is not None:
            assert u.sp.replace(".", "", 1).isdigit() and u.sp.endswith(".00")
        if u.num_of_rating is not None:
            assert isinstance(u.num_of_rating, int) and u.num_of_rating >= 0
    assert all(u.mrp != "0.00" for u in units)  # a missing MRP is None, never 0
    sample = [u for kw in ("men hoodie", "women saree", "men chinos", "kids party wear", "women tunic") for u in _all_units(kw, H1)[0] if u.product_type != "SB"]
    assert any(u.mrp is None for u in sample) and any(u.rating is None for u in sample)  # missing values do occur
