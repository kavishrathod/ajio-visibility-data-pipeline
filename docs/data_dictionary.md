# Data dictionary

All timestamps use ISO 8601 UTC strings ending in `Z` unless the value is explicitly a date parsed from an input fixture. `scheduled_hour` is the IST hour slot (stored as a UTC instant) and `time_stamp` is the response fetch time.

## `visibility_product`

| Field | Meaning |
|---|---|
| `time_stamp` | Time the page containing this placement was fetched, in UTC. |
| `platform` | Platform name (`AJIO`). |
| `platform_code` | Page surface the unit came from. This project only collects keyword search results, so it is always `search`. (A brand store would use `brandstore`; not implemented.) |
| `keyword` | Configured search target. |
| `product_name` | Displayed product/banner name from the synthetic fixture. |
| `sp` | Parsed selling price as a decimal-compatible value; ambiguous/missing values are NULL. |
| `mrp` | Parsed MRP as a decimal-compatible value; ambiguous/missing values are NULL. |
| `rating` | Numeric rating when it can be parsed unambiguously. |
| `num_of_rating` | Parsed rating count; `K` and `M` suffixes are normalized to integers. |
| `tag` | Optional label such as bestseller/new. |
| `deal` | Optional deal text. |
| `product_image_url` | Product or banner image URL as named in the assessment fields. |
| `absolute_rank` | Unique display position across all placements and pages for a keyword-hour. |
| `relative_rank` | Position within the same type (`Organic`, `SP`, or `SB`). |
| `product_type` | `Organic`, `SP` (sponsored product), or `SB` (sponsored brand/banner). Placement labels are synthetic in this mock project. |
| `campaign_id` | Campaign identifier when provided; only synthetic values appear in fixtures. |
| `product_id` | Stable product key, preferably supplied by data or derived from product URL path. Can be NULL for a brand banner. |
| `product_url` | Product URL if present. |
| `run_id` | Run that most recently wrote this normalized position. |
| `target_id` | Foreign key to `scrape_target`. |
| `scheduled_hour` | Hour being measured; supports reruns/backfills. |
| `page_number` | Source page where this placement was observed. |
| `raw_payload_ref` | Relative path to raw HTML snapshot. |
| `parse_status` | `ok` for normalized rows. Failures are represented in target/run tables, not fabricated product rows. |
| `is_mock` | `1` for synthetic fixtures; intended to stay `1` unless a separately approved source adapter is added. |

## Operational tables

- **`scrape_target`**: one configured keyword per platform, enabled flag, cadence, max pages, priority.
- **`scrape_run`**: run-level lifecycle, trigger, scheduled hour, counts, adapter mode, errors, retry count.
- **`raw_snapshot`**: fetched response metadata, checksum, local file path, status, response headers, mock flag.
- **`target_hour_status`**: one status per platform/keyword/hour; `expected=1` means one slot was due and `observed=1` means it completed with `success` or a valid `zero_result`. `row_count` is the normalized row count; parse failures and incomplete reasons remain explicit.
- **`quarantine_record`**: one row per rejected card, placement or page. Columns: `run_id`, `platform`, `target_id`, `keyword`, `scheduled_hour`, `page_number`, `record_type` (`card` / `unit` / `page`), `record_index` (card position on the page, or entry order within the target; 0 for a page), `stage` (`parse` / `validate` / `dedupe`), `reason_code`, `reason_detail`, `payload_json` (card attributes or the parsed unit), `raw_payload_ref` (the raw page it came from), `is_mock`, `created_at`. Unique on `(run_id, target_id, page_number, record_type, record_index, reason_code)`. Reason codes are listed in `docs/quarantine.md`.
- **`alert_incident`**: aggregated alert per hour, send cooldown, resolution, recovery notification.
- **`pipeline_lock`**: short-lived process lock that prevents overlapping runs.

## Gold views

`gold_hour_summary` (coverage and volume per hour), `gold_keyword_hour` (unit mix, paid share, price spread per keyword and hour), `gold_product_placement` (best organic rank versus best sponsored rank per product), `gold_quarantine_summary` (quarantined records by reason, latest attempt per target-hour). Definitions are in `sql/schema.sql` and explained in `docs/gold_layer.md`.

## Rank and dedup semantics

Ranks are assigned in observed top-to-bottom order after duplicate placements within a type/campaign are dropped. `SP` and `Organic` versions of the same product remain separate. A sponsored-brand banner can have no product ID; its campaign ID (or fallback banner identity) identifies the placement.

## Statuses

| Level | Value | Meaning |
|---|---|---|
| target-hour | `success` | At least one valid page parsed; all attempted pages ok. Complete. |
| target-hour | `zero_result` | Page 1 had an explicit no-results marker. Complete. |
| target-hour | `partial` | Page 1 parsed, a later page failed (parse failure, or fetch retries exhausted). Page-1 rows are kept. Not complete. |
| target-hour | `parse_failed` | Grid missing/renamed or no card passed validation. No rows written. |
| target-hour | `blocked` | HTTP 401/403, 429 beyond budget, or a challenge page. Not retried. |
| target-hour | `failed` | Retries exhausted, unexpected error, or `load_failed` (database unavailable). |
| target-hour | `running` | The run is currently collecting this target. Becomes `missing` after the grace period if its run is gone. |
| target-hour | `missing` | No terminal status after the grace period. |
| target-hour | `not_yet_due` | Grace period has not elapsed. |
| run | `running` / `success` / `partial` / `failed` | Run lifecycle. |
| run | `skipped_overlap` | Fired while another run held the lock; fetched nothing. |

## Added columns and files

- `target_hour_status.anomalies`: JSON list of pagination-drift findings, e.g. `{"product_id": "333", "kept_on_page": 1, "repeated_on_page": 2}`; NULL when clean.
- `alert_incident.run_id`, `conditions` (JSON list of active triggers), `fingerprint` (hash of the trigger set; a change causes an immediate resend), `last_error` (delivery failure note).
- `alert_incident.alert_type` is the highest-priority active trigger: `run_failed`, `blocked`, `parser_errors`, `missing_slots`, `completeness`, `row_drop`, `stale_data`. One incident per platform-hour holds all active triggers.
- Raw sidecar `*.meta.json`: `run_id`, `scheduled_hour`, `keyword`, `page`, `http_status`, `fetched_at`, `is_mock`, `headers`, `sha256`. Used by `--reload-raw`.
- `scrape_run.trigger`: `scheduled`, `manual`, `backfill`, or `reload`.

## Time

All stored times are UTC ISO-8601 ending in `Z`. `scheduled_hour` is the slot: the top of an IST hour (UTC+5:30) stored as a UTC instant, so 10:00 IST is `...T04:30:00Z` (fixed when the run starts); `time_stamp` is the real fetch time, which can fall in a later hour.
