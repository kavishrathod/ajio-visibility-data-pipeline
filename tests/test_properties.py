"""Property-based tests (Hypothesis) for the value parsers, deduplication and rank assignment.

Example-based tests check the cases someone thought of. These state a rule that must hold for every input
and let Hypothesis search for a counterexample. See docs/property_tests.md.
"""
import string
from decimal import Decimal

from hypothesis import given, strategies as st

from src.parsers.product_parser import ProductUnit, parse_count, parse_price, parse_rating, product_key
from src.pipeline.ranking import RankState, assign_ranks
from src.pipeline.validator import deduplicate_units, placement_key, validate_entries, validate_units

# ----------------------------------------------------------------------------- price parsing
amounts = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("9999999.99"), places=2, allow_nan=False, allow_infinity=False)


def indian_grouping(whole: int) -> str:
    """1234567 -> '12,34,567'."""
    digits = str(whole)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def render(amount: Decimal, grouping: str, template: str) -> str:
    whole, fraction = f"{amount:.2f}".split(".")
    if grouping == "western":
        whole = f"{int(whole):,}"
    elif grouping == "indian":
        whole = indian_grouping(int(whole))
    number = whole if (fraction == "00" and grouping != "plain-keep") else f"{whole}.{fraction}"
    return template.format(number)


templates = st.sampled_from(["₹{}", "₹ {}", "Rs. {}", "Rs {}", "INR {}", "MRP: ₹{}", "{}", "  ₹{}  "])
groupings = st.sampled_from(["plain", "western", "indian"])


@given(amounts, groupings, templates)
def test_price_text_round_trips_to_the_exact_decimal(amount, grouping, template):
    assert parse_price(render(amount, grouping, template)) == f"{amount:.2f}"


@given(amounts, amounts, st.sampled_from([" - ", "-", " – ", " to "]), st.sampled_from(["₹{}", "Rs. {}", "{}"]))
def test_a_price_range_is_never_guessed(low, high, separator, template):
    text = template.format(f"{low:.2f}") + separator + template.format(f"{high:.2f}")
    assert parse_price(text) is None


@given(st.text(alphabet=string.ascii_letters + " ₹.,:-—/", max_size=40))
def test_text_without_digits_is_never_a_price_and_never_zero(text):
    assert parse_price(text) is None


@given(st.text(max_size=60))
def test_parsers_never_crash_and_only_return_well_formed_values(text):
    price, count, rating = parse_price(text), parse_count(text), parse_rating(text)
    assert price is None or (len(price.split(".")) == 2 and len(price.split(".")[1]) == 2 and Decimal(price) >= 0)
    assert count is None or (isinstance(count, int) and count >= 0)
    assert rating is None or 0 <= rating <= 5


@given(st.text(max_size=60))
def test_parsing_a_parsed_price_changes_nothing(text):
    price = parse_price(text)
    if price is not None:
        assert parse_price(price) == price


# ----------------------------------------------------------------------------- count and rating parsing
@given(st.integers(min_value=0, max_value=9_999_999), st.booleans())
def test_plain_and_bracketed_counts_with_separators_are_exact(count, bracketed):
    text = f"{count:,}"
    assert parse_count(f"({text})" if bracketed else text) == count


@given(st.integers(min_value=1, max_value=999), st.integers(min_value=0, max_value=9))
def test_k_and_m_suffixes_scale_exactly(whole, tenth):
    assert parse_count(f"{whole}.{tenth}K") == whole * 1000 + tenth * 100
    assert parse_count(f"{whole}.{tenth}k") == whole * 1000 + tenth * 100
    assert parse_count(f"{whole}.{tenth}M") == (whole * 10 + tenth) * 100_000


@given(st.sampled_from(["", "  ", "-", "—", "n/a", "N/A", "na", "not rated", "()", None]))
def test_a_missing_count_is_null_never_zero(text):
    assert parse_count(text) is None


@given(st.integers(min_value=0, max_value=50), st.sampled_from(["{}", "Rated {} out of 5", "{}/5", "{} ★"]))
def test_valid_ratings_round_trip(tenths, template):
    assert parse_rating(template.format(f"{tenths / 10:.1f}")) == tenths / 10


@given(st.integers(min_value=51, max_value=99))
def test_an_out_of_range_rating_is_null_not_a_fragment_of_itself(tenths):
    # "7.5" must not be read as the in-range fragment "5".
    assert parse_rating(f"{tenths // 10}.{tenths % 10}") is None


# ----------------------------------------------------------------------------- product key
@given(
    st.integers(min_value=100000, max_value=99999999),
    st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=8),
    st.text(alphabet=string.ascii_lowercase + "-", min_size=1, max_size=30).filter(lambda s: s.strip("-")),
    st.dictionaries(st.text(alphabet=string.ascii_lowercase + "_", min_size=1, max_size=8),
                    st.text(alphabet=string.ascii_letters + string.digits, max_size=10), max_size=4),
)
def test_product_key_ignores_the_title_slug_and_tracking_parameters(pid, colour, slug, params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://www.ajio.com/{slug}/p/{pid}_{colour}" + (f"?{query}" if query else "")
    assert product_key(url) == f"{pid}_{colour}"


# ----------------------------------------------------------------------------- deduplication
unit_strategy = st.builds(
    ProductUnit,
    product_type=st.sampled_from(["Organic", "SP", "SB"]),
    product_name=st.sampled_from(["Alpha", "Beta", "Gamma"]),
    product_id=st.sampled_from([None, "1", "2", "3"]),
    campaign_id=st.sampled_from([None, "c1", "c2"]),
)
units_strategy = st.lists(unit_strategy, max_size=25)


def keys(units):
    return [placement_key(u) for u in units]


@given(units_strategy)
def test_dedup_keeps_exactly_one_unit_per_placement_and_the_first_one(units):
    kept, dropped = deduplicate_units(units)
    assert len(kept) == len(set(keys(units)))
    assert dropped == len(units) - len(kept)
    first_by_key = {}
    for unit in units:
        first_by_key.setdefault(placement_key(unit), unit)
    assert all(first_by_key[placement_key(u)] is u for u in kept)          # first occurrence wins
    assert [id(u) for u in kept] == sorted((id(u) for u in kept), key=lambda i: [id(x) for x in units].index(i))  # order kept


@given(units_strategy)
def test_dedup_is_idempotent(units):
    once, _ = deduplicate_units(units)
    twice, dropped_again = deduplicate_units(once)
    assert twice == once and dropped_again == 0


@given(st.lists(st.integers(min_value=1, max_value=50), min_size=1, max_size=15, unique=True),
       st.sampled_from(["Organic", "SP"]))
def test_the_title_alone_never_decides_a_duplicate(ids, product_type):
    units = [ProductUnit(product_type=product_type, product_name="Same Title", product_id=str(i)) for i in ids]
    kept, dropped = deduplicate_units(units)
    assert len(kept) == len(units) and dropped == 0


@given(st.sampled_from(["1", "2", "3"]))
def test_the_same_product_as_sp_and_organic_is_two_placements(product_id):
    organic = ProductUnit(product_type="Organic", product_name="X", product_id=product_id)
    sponsored = ProductUnit(product_type="SP", product_name="X", product_id=product_id, campaign_id="c1")
    kept, dropped = deduplicate_units([organic, sponsored, organic, sponsored])
    assert [u.product_type for u in kept] == ["Organic", "SP"] and dropped == 2


entry_strategy = st.builds(
    lambda unit, page, rating: {"unit": ProductUnit(**{**unit.__dict__, "rating": rating}), "page_number": page,
                                "raw_payload_ref": "raw.html", "is_mock": 1},
    unit_strategy, st.sampled_from([1, 2]), st.sampled_from([None, 4.0, 9.5]),     # 9.5 breaks the rating rule
)


@given(st.lists(entry_strategy, max_size=25))
def test_every_entry_is_accepted_or_rejected_and_the_two_implementations_agree(entries):
    accepted, rejected = validate_entries(entries)
    accepted_ids = {id(e) for e in accepted}
    rejected_ids = {id(r["entry"]) for r in rejected}
    assert accepted_ids.isdisjoint(rejected_ids)
    assert accepted_ids | rejected_ids == {id(e) for e in entries}          # nothing silently disappears
    assert all(r["reason_code"] for r in rejected) and all(r["stage"] in {"validate", "dedupe"} for r in rejected)
    # same accepted units as the older unit-level implementation
    old_accepted, _ = validate_units(e["unit"] for e in entries)
    assert [id(e["unit"]) for e in accepted] == [id(u) for u in old_accepted]


@given(st.lists(entry_strategy, max_size=25))
def test_duplicate_reason_matches_whether_the_pages_differ(entries):
    _, rejected = validate_entries(entries)
    first_page = {}
    for entry in entries:
        if not any(r["entry"] is entry and r["stage"] == "validate" for r in rejected):
            first_page.setdefault(placement_key(entry["unit"]), entry["page_number"])
    for r in rejected:
        if r["stage"] == "dedupe":
            kept_page = first_page[placement_key(r["entry"]["unit"])]
            expected = "duplicate_placement" if kept_page == r["entry"]["page_number"] else "cross_page_duplicate"
            assert r["reason_code"] == expected


# ----------------------------------------------------------------------------- rank assignment
types_strategy = st.lists(st.sampled_from(["Organic", "SP", "SB"]), max_size=60)


@given(types_strategy)
def test_ranks_are_continuous_overall_and_within_each_type(types):
    ranks, state = assign_ranks(types)
    assert [a for a, _ in ranks] == list(range(1, len(types) + 1))
    for product_type in {"Organic", "SP", "SB"}:
        relative = [r for (_, r), t in zip(ranks, types) if t == product_type]
        assert relative == list(range(1, len(relative) + 1))
    assert state.absolute == len(types)


@given(types_strategy, st.lists(st.integers(min_value=0, max_value=60), max_size=4))
def test_splitting_the_results_into_pages_never_changes_the_ranks(types, cuts):
    whole, _ = assign_ranks(types)
    bounds = sorted({min(c, len(types)) for c in cuts} | {0, len(types)})
    state, paged = RankState(), []
    for start, end in zip(bounds, bounds[1:]):
        page_ranks, state = assign_ranks(types[start:end], state)
        paged.extend(page_ranks)
    assert paged == whole
