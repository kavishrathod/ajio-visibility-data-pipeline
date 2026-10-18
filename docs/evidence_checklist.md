# Evidence pack

The screenshots are in `screenshots/`. They come from my own runs on mock data, are unedited, and the dashboard
screenshots show the MOCK DATA ONLY banner.

## Required evidence

| # | Evidence | File | How it was produced |
|---|---|---|---|
| 1 | Source inspection with the URL visible | `01_source.png`, `02_source_inspection.png` | Manual viewing of the AJIO search page for "white kurta for men" in Chrome, with DevTools (Network tab) open; no automation |
| 2 | A successful run: run_id, pages, products, status | `04_successful_run.png` | `python -m src.main --run-once` (final JSON), or the dashboard Run history tab |
| 3 | Raw snapshots in timestamped partitions | `05_bronze_raw_data.png` | `dir data\raw /s`, showing `platform=AJIO/date=.../hour=.../<run_id>/` |
| 4 | Normalised rows with SB, SP and Organic | `06_normalized_product_records.png` | Dashboard, Visibility products tab (keyword, product_name, sp, mrp, absolute_rank, relative_rank, product_type, scheduled_hour, run_id) |
| 5 | Scheduler with a completed run | `08_hourly_scheduler.png` | `python -m src.main --schedule` after a cycle; `config/cron.example` for the OS-scheduler alternative |
| 6 | Dashboard coverage grid | `09_coverage_grid.png` | Dashboard, Coverage grid tab, after `--demo` |
| 7 | A deliberately missing slot, flagged, with the incident and recovery | `09_coverage_grid.png`, `10_alert_incident_recovery.png` | One hour left uncollected, then `--check-completeness --hour <slot>`; the grid shows `missing` and Alert incidents shows the incident |
| 8 | Alert emails | `11_alert_email_missing_data.png`, `12_alert_email_recovery.png` | Files written to `data/outbox/` by the missing-slot alert and the recovery after backfill |
| 9 | Full test output, including the curveball tests | `14_test_results.png` | `python -m pytest -v` |

## Additional screenshots

| File | Shows | How it was produced |
|---|---|---|
| `03_dashboard_overview.png` | Dashboard overview | `python -m streamlit run src/dashboard/app.py` |
| `07_gold_aggregates.png` | Gold aggregates tab | Dashboard, Gold aggregates tab |
| `13_quarantine_data.png` | Quarantined records | Dashboard, Quarantine tab, or `python scripts/show_quarantine.py --details` |

## Other checks

- Duplicate spike: `python -m pytest -q tests/test_duplicate_spike.py` (detection, thresholds, baseline, recovery).
- Brand comparison: `python -m pytest -q tests/test_brand.py`; dashboard, Gold aggregates tab, *Brand: organic rank versus sponsored placements*.
- Test-suite cost on a given machine: `python scripts/fs_benchmark.py`.

- Idempotency: run the same hour twice, then `python scripts/check_idempotency.py`. Rows per slot equal the
  distinct target and rank count.
- Clean clone: results are recorded in the README (113 passed, demo ran, coverage grid exported to CSV and checked).
