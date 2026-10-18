# Curveball scenarios: fixture and test map

| ID | Scenario | Fixture / simulated response | Test (file::name) | Status |
|---|---|---|---|---|
| I-1 | Silent layout change | `layout_changed.html`, `layout_changed_jsonld_present.html` | `test_orchestrator::test_parser_failure_is_not_recorded_as_zero_result`, `test_parsing::test_layout_change_is_not_mistaken_for_zero_results`, `test_jsonld::test_json_ld_does_not_rescue_a_page_whose_grid_is_missing` | Full |
| I-2 | Genuine zero results | `zero_results.html` | `test_parsing::test_valid_zero_results_is_not_a_parse_failure`, `test_orchestrator::test_full_50_keyword_mock_run...` (2 zero-result keywords complete, no alert) | Full |
| I-3 | Mixed placement types | `mixed_placements.html`, generator | `test_ranking::*`, `test_parsing::test_mixed_placements_keep_paid_and_organic_separate`, `test_synthetic_mock::test_listing_matches_the_worked_example_ranks` | Full |
| I-4 | Pagination drift | `pagination_drift_page1.html`, `pagination_drift_page2.html` | `test_curveballs::test_i4_*` | Partial (see KNOWN_GAPS 3) |
| I-5 | Messy values | `messy_values.html`, generator | `test_parsing::test_messy_values_are_null_not_zero...`, `test_parsing::test_price_count_rating_and_product_key_helpers` | Full |
| I-6 | Same product twice | `messy_values.html`, generator | `test_curveball_audit::test_same_product_sponsored_and_organic...`, `test_synthetic_mock::test_same_product_appears_as_sp_and_organic...` | Full |
| I-7 | Throttled and blocked | simulated 429/403 responses, `bot_challenge.html` | `test_curveballs::test_i7_*`, `test_fetcher::*` | Full (mock) |
| I-8 | Hour boundary | simulated late fetch time | `test_curveballs::test_i8_*`, `test_curveball_audit::test_hour_input_is_normalized...` | Full (IST slots) |
| I-9 | Overlapping runs | blocking adapter + thread | `test_curveballs::test_i9_*`, `test_database::test_global_lock_rejects_overlapping_runs` | Full |
| I-10 | Late backfill | missing 09:00 slot | `test_curveballs::test_i10_late_backfill...` | Full |
| I-11 | Database down mid-run | patched database failures | `test_curveballs::test_i11_*` | Full (mid-run) |
| I-12 | Alert storm | 40 of 50 targets fail | `test_curveballs::test_i12_forty_failures...`, `test_alerts::test_incident_dedup_cooldown_and_single_recovery` | Full |

## Quarantine evidence

Rejected records for these scenarios are also kept in `quarantine_record` (see `docs/quarantine.md`); tests are in `tests/test_quarantine.py`.

| ID | What is quarantined | Test |
|---|---|---|
| I-1 | The page, as `page_parse_failed`, with the raw page path (a healthy `zero_result` page is not quarantined) | `test_unparseable_and_blocked_pages_are_quarantined_but_a_zero_result_is_not` |
| I-4 | The later copy of a placement repeated across pages, as `cross_page_duplicate`, naming the page that was kept | `test_cross_page_duplicate_is_quarantined_and_names_the_page_that_was_kept` |
| I-6 | A true duplicate of the same placement, as `duplicate_placement`; the same product as SP and Organic is not a duplicate | `test_rejected_cards_and_duplicates_are_quarantined_with_reason_and_payload` |
| I-7 | The blocked or challenge page, as `page_blocked` | `test_unparseable_and_blocked_pages_are_quarantined_but_a_zero_result_is_not` |
| I-11 | Rows are rebuilt by `--reload-raw`; a failed quarantine write never changes a status | `test_reload_raw_rebuilds_quarantine_without_refetching`, `test_a_failed_quarantine_write_never_changes_the_target_status` |

## Property-based coverage

Generated-input tests in `tests/test_properties.py` (see `docs/property_tests.md`) also exercise I-3 (rank continuity across pages), I-5 (price, count and rating parsing) and I-6 (the placement key and deduplication) beyond the fixed fixtures. They found and led to fixes of two parser bugs: an out-of-range rating read as a fragment of itself, and a wrong product key for a URL whose title slug is `p`.
