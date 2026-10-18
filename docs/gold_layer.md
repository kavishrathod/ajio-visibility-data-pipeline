# Gold layer

Bronze is the raw snapshot (files plus the `raw_snapshot` table), Silver is `visibility_product`, and
Gold is a set of read-only SQL views defined in `sql/schema.sql`. All data is synthetic mock data.

## Why views, not tables
- They always agree with Silver and the status ledger, so there is nothing to refresh or reconcile.
- A rerun or a late backfill of an hour changes the aggregates automatically and cannot create duplicate
  aggregate rows (tested in `tests/test_gold.py::test_gold_views_do_not_double_count_after_a_rerun`).
- Cost: they are recomputed on read. At this scale (50 keywords x about 32 rows x 24 hours a day) that is trivial;
  at 100x the first change would be materialising them per hour (see DECISIONS.md, question 6).

## Views

| View | Grain | Answers |
|---|---|---|
| `gold_hour_summary` | platform, hour | Coverage and volume: targets, complete, zero_result, missing, problem, pending, rows, completeness_pct |
| `gold_keyword_hour` | keyword, hour | Unit mix (organic, SP, SB), paid share, distinct products, min/avg/max selling price, average rating. Built from the status ledger, so a genuine zero-result keyword appears with 0 units and status `zero_result`, and a missing one is visible |
| `gold_quarantine_summary` | platform, hour, reason | Records rejected on the way to Silver, by record type, stage and reason code, counting only the latest attempt per target-hour (`docs/quarantine.md`) |
| `gold_product_placement` | product, keyword, hour | Best organic rank vs best sponsored rank for the same product, and how many placements of each. Both set = the product was shown as organic and as a paid unit (I-6) |

## Limits
- `gold_hour_summary` reflects statuses that have been written. A target that was never run has no row until
  `--check-completeness` (or the scheduler) materialises it as `missing`.
- Brand-level comparison is not modelled. The output record has no brand field, and parsing a brand out of
  `product_name` would be a guess. Product-level comparison uses `product_id`, which is reliable.
- Rank movement across hours is not built (listed stretch work).

## Try it
```
python -m src.main --run-once
python -m streamlit run src/dashboard/app.py     # tab: Gold aggregates
```
Or from Python / any SQLite client: `SELECT * FROM gold_hour_summary ORDER BY scheduled_hour DESC;`
