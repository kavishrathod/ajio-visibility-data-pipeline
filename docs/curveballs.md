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
