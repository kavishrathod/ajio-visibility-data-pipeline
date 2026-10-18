# Quarantine layer

Anything rejected on the way from the raw page to the normalized table is kept in `quarantine_record`
with a machine-readable reason, the offending payload, and a pointer to the raw page it came from.
Before this layer a rejected card was only a log warning and a rejected duplicate was only a count.
All data is synthetic mock data.

## What is quarantined

| `record_type` | `stage` | `reason_code` | When |
|---|---|---|---|
| `card` | parse | `card_missing_name` | A product card has no name (and no JSON-LD entry supplies one) |
| `card` | parse | `card_missing_identity` | A non-banner card has neither a product id nor a URL |
| `unit` | validate | `missing_product_name`, `invalid_product_type`, `rating_out_of_range`, `negative_rating_count` | A parsed placement breaks a validation rule |
| `unit` | dedupe | `duplicate_placement` | The same placement (type + product + campaign) appears twice on one page; first occurrence kept |
| `unit` | dedupe | `cross_page_duplicate` | The same placement appears on a later page (pagination drift, I-4); first occurrence kept |
| `page` | parse | `page_parse_failed` | Grid missing or renamed, or no card passed validation (I-1) |
| `page` | parse | `page_blocked` | 403, challenge page, or other block marker (I-7) |

## What is not quarantined, and why
- **A genuine zero result.** It is a healthy outcome (`zero_result`), not a rejection (I-2).
- **A value that is normalised to NULL** (a price range, an out-of-range rating the parser nulls, a missing MRP).
  The record is still valid; only the field is empty. Quarantining it would flood the table with healthy rows.
- **A fetch that never produced a page** (timeout, retries exhausted). There is no payload to keep; the target is
  `failed` or `partial` in `target_hour_status`.

The repeated placements dropped at the deduplication stage are also counted per target-hour (`duplicate_count`); a
sharp rise in that count opens a duplicate-spike incident (`docs/duplicate_spike.md`), and the quarantine rows are the
evidence to look at.

## Behaviour
- **Evidence, not a dependency.** A failed quarantine write is logged in the run's `db_errors` but never changes a
  target's status or blocks loading valid rows. The rows can be rebuilt with `--reload-raw`, because the raw page is
  always written first.
- **Append-only per run.** Unique key `(run_id, target_id, page_number, record_type, record_index, reason_code)` with
  `INSERT OR IGNORE`, so one run never stores a record twice. A rerun or reload is a new run, so earlier attempts stay
  as history.
- **Latest attempt for reporting.** `gold_quarantine_summary` counts a row only when its run is the one that last wrote
  that target-hour status (`target_hour_status.last_run_id`). Reruns therefore never double the totals.
- **Traceable.** `raw_payload_ref` is the exact raw HTML file; `payload_json` holds the card attributes or the parsed
  unit; `is_mock` is carried through.

## Try it
```
python -m src.main --run-once
python scripts/show_quarantine.py --details
python -m streamlit run src/dashboard/app.py       # tab: Quarantine
```
The standard mock run quarantines one repeated placement (for the keyword `women kurta set`), which is the same
event the log line `Dropped 1 repeated placement(s)` reports. Fixture `tests/fixtures/quarantine_cards.html` produces
every card-level reason.

## Not built
- No automatic alert on a high quarantine rate (the existing parser-error alert covers whole-page failures).
- No retention or purge, and no "release / reprocess" workflow for a quarantined record (replay is per hour, via
  `--reload-raw`).
