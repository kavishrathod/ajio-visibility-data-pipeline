"""Brand field: explicit labels only, normalised, and compared with sponsored placements in the Gold layer."""
import json
import string

import pytest
from hypothesis import given, strategies as st

from src.parsers.product_parser import parse_products
from src.pipeline.brands import MAX_BRAND_LENGTH, brand_key, clean_brand, load_brand_aliases, normalize_brand
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import ScriptedAdapter, fixture_text, isolated_config, no_sleep, resp

HOUR = "2026-10-16T14:30:00Z"


def _db(config):
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    return db


def _run(config):
    def fn(keyword, page, n):
        return resp(fixture_text("brand_placements.html"), keyword=keyword) if page == 1 else resp(fixture_text("zero_results.html"), keyword=keyword, page=2)
    return run_pipeline(config, HOUR, adapter_override=ScriptedAdapter(fn), sleeper=no_sleep)


def _by_brand(db):
    return {r["brand_key"]: r for r in db.query("SELECT * FROM gold_brand_placement")}


# ----------------------------------------------------------------------------- normalisation
def test_case_spacing_and_unicode_variants_share_one_key_and_display_text_is_cleaned():
    for variant in ["Fakely", "FAKELY", "  fakely  ", "Fakely\u00a0", "Ｆａｋｅｌｙ", "ＦＡＫＥＬＹ"]:
        assert brand_key(variant) == "fakely"
    assert clean_brand("  Fakely   Co  ") == "Fakely Co"
    assert normalize_brand("Ｆａｋｅｌｙ") == ("Fakely", "fakely")
    assert brand_key("H&M") == "h&m" and brand_key("HM") == "hm"                 # & separates different brands
    assert brand_key("U.S. Polo Assn.") == "u s polo assn" != brand_key("US Polo Assn")   # handled by an alias, not guessed


@pytest.mark.parametrize("value", [None, "", "   ", "N/A", "n/a", "None", "null", "Unknown", "-", "—", "...", "x" * (MAX_BRAND_LENGTH + 1)])
def test_missing_placeholder_and_implausible_brands_become_null(value):
    assert normalize_brand(value) == (None, None)


def test_curated_aliases_merge_variants_and_are_validated(tmp_path):
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    (root / "config" / "brand_aliases.json").write_text(json.dumps({"aliases": {"Alpha Co.": "Alpha", "U.S. POLO ASSN": "US Polo Assn"}}), encoding="utf-8")
    aliases = load_brand_aliases(root)
    assert aliases == {"alpha co": "Alpha", "u s polo assn": "US Polo Assn"}
    assert normalize_brand("ALPHA CO", aliases) == ("Alpha", "alpha")
    assert normalize_brand("u.s. polo assn.", aliases) == ("US Polo Assn", "us polo assn")
    assert normalize_brand("Beta", aliases) == ("Beta", "beta")
    assert load_brand_aliases(tmp_path / "nowhere") == {}
    (root / "config" / "brand_aliases.json").write_text(json.dumps({"aliases": {"Alpha": ""}}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid alias"):
        load_brand_aliases(root)


@given(st.text(alphabet=string.ascii_letters + string.digits + " &.-'", max_size=30))
def test_normalising_twice_changes_nothing_and_never_returns_an_empty_brand(text):
    brand, key = normalize_brand(text)
    assert (brand is None) == (key is None)
    if brand is not None:
        assert brand and key
        assert normalize_brand(brand) == (brand, key)


@given(st.text(alphabet=string.ascii_letters, min_size=1, max_size=20), st.sampled_from(["{}", " {}", "{}  ", " {} "]), st.booleans())
def test_the_key_ignores_case_and_padding(word, padding, upper):
    variant = padding.format(word.upper() if upper else word.lower())
    assert brand_key(variant) == brand_key(word)


# ----------------------------------------------------------------------------- parsing: explicit field only
def test_the_brand_is_read_from_the_explicit_field_and_never_from_the_title():
    html = ('<section data-testid="product-grid">'
            '<article class="product-card" data-kind="ORGANIC" data-name="Fakely Slim Jeans" data-product-id="1" data-url="https://www.ajio.com/a/p/1_blue" data-brand="Fakely"></article>'
            '<article class="product-card" data-kind="ORGANIC" data-name="Fakely Slim Jeans Two" data-product-id="2" data-url="https://www.ajio.com/b/p/2_blue"></article>'
            '<article class="product-card" data-kind="ORGANIC" data-name="Plain Jeans" data-product-id="3" data-url="https://www.ajio.com/c/p/3_blue"><span data-testid="brand">Samplr</span></article>'
            '</section>')
    first, second, third = parse_products(html).units
    assert first.brand == "Fakely"
    assert second.brand is None           # "Fakely" is in the title, but the page gave no brand: not inferred
    assert third.brand == "Samplr"        # the displayed brand label works as well as the attribute


# ----------------------------------------------------------------------------- Silver and Gold
def test_brand_columns_and_the_organic_versus_sponsored_comparison(tmp_path):
    config = isolated_config(tmp_path, ["men white t-shirt"])
    summary = _run(config)
    assert summary["status"] == "success"
    db = _db(config)

    silver = {r["absolute_rank"]: (r["brand"], r["brand_key"]) for r in db.query("SELECT absolute_rank, brand, brand_key FROM visibility_product")}
    assert silver[1] == ("Alpha", "alpha") and silver[2] == ("ALPHA", "alpha")      # "ALPHA " cleaned, same key
    assert silver[7] == (None, None)       # no brand label: the title "Alpha Mock Shirt" is not used
    assert silver[8] == (None, None)       # "N/A" placeholder
    assert silver[10] == ("Alpha Co.", "alpha co")                                  # no alias configured: a separate brand

    brands = _by_brand(db)
    assert set(brands) == {"alpha", "beta", "gamma", "delta", "alpha co"}
    alpha = brands["alpha"]
    assert alpha["brand"] == "Alpha"                                                # spelling of the brand's highest-ranked unit
    assert (alpha["organic_units"], alpha["best_organic_rank"], alpha["sp_units"], alpha["best_sp_rank"], alpha["sb_units"]) == (1, 2, 1, 1, 1)
    assert (alpha["best_paid_absolute_rank"], alpha["best_organic_absolute_rank"], alpha["paid_position_gain"], alpha["paid_only"]) == (1, 4, 3, 0)
    beta = brands["beta"]                                                           # organic above its own sponsored unit
    assert (beta["best_organic_rank"], beta["best_sp_rank"], beta["paid_position_gain"]) == (1, 2, -2)
    gamma = brands["gamma"]                                                         # organic only
    assert (gamma["organic_units"], gamma["best_organic_rank"], gamma["sp_units"], gamma["best_sp_rank"], gamma["paid_position_gain"]) == (1, 3, 0, None, None)
    delta = brands["delta"]                                                         # paid only
    assert (delta["organic_units"], delta["best_organic_rank"], delta["sp_units"], delta["best_sp_rank"], delta["paid_only"]) == (0, None, 1, 4, 1)

    coverage = db.query("SELECT * FROM gold_brand_coverage")[0]
    assert (coverage["units"], coverage["units_with_brand"], coverage["brand_coverage_pct"]) == (10, 8, 80.0)


def test_a_curated_alias_merges_a_variant_into_its_brand(tmp_path):
    config = isolated_config(tmp_path, ["men white t-shirt"])
    (config.root / "config" / "brand_aliases.json").write_text(json.dumps({"aliases": {"Alpha Co.": "Alpha"}}), encoding="utf-8")
    _run(config)
    brands = _by_brand(_db(config))
    assert set(brands) == {"alpha", "beta", "gamma", "delta"}
    alpha = brands["alpha"]
    assert (alpha["organic_units"], alpha["best_organic_rank"], alpha["best_organic_absolute_rank"]) == (2, 2, 4)


def test_a_rerun_does_not_duplicate_brand_rows(tmp_path):
    config = isolated_config(tmp_path, ["men white t-shirt"])
    _run(config)
    _run(config)
    db = _db(config)
    assert db.query("SELECT COUNT(*) AS n FROM visibility_product")[0]["n"] == 10
    assert db.query("SELECT organic_units FROM gold_brand_placement WHERE brand_key='alpha'")[0]["organic_units"] == 1
