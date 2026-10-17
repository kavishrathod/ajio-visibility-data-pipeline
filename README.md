# AJIO Visibility Data Pipeline

[![CI](https://github.com/kavishrathod/ajio-visibility-data-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/kavishrathod/ajio-visibility-data-pipeline/actions)

A local-first hourly keyword-visibility pipeline for 50 configured
keywords. It records organic results, sponsored products (`SP`), and
sponsored-brand banners (`SB`), normalizes product fields and ranks,
stores raw snapshots, tracks target-hour completeness, and records
alert/recovery incidents.

> **Mock data only.** Automated live AJIO collection is disabled. The
> project's source research found the relevant `/search` and `/api/*`
> paths disallowed by AJIO's `robots.txt`; the live adapter fails
> closed. All product names, prices, ratings, campaigns, and placements
> in this demo are synthetic or fixture-based, not live AJIO
> observations. See
> [`docs/source_research.md`](docs/source_research.md).

## Features

-   50 configured keywords, including two intended zero-result keywords.
-   Distinguishes explicit `zero_result` pages from parser/fetch
    failures.
-   Normalized placement rows with ranks, prices, ratings, campaign
    metadata, and lineage.
-   Mock pages mirror the one layer of the real search page that was
    observed (a JSON-LD `ItemList` with name, image, URL and position);
    price, rating and placement fields on the cards are simulated.
-   Quarantine layer: rejected cards, placements and pages are kept with
    a reason code, the payload, and a pointer to the raw page.
-   Slots are IST hours (10:00 IST is stored as `04:30Z`).
-   Raw HTML snapshots plus JSON sidecars saved before database loading.
-   SQLite run ledger, target-hour statuses, product placements, alert
    incidents, and overlap lock.
-   Deduplication and idempotent upserts for reruns and backfills.
-   Retry/backoff, bounded `Retry-After`, rate limiting, and
    stop-on-block/challenge behaviour exercised through mocks/tests.
-   APScheduler hourly scheduling, completeness checks, aggregated
    alerts, and recovery handling.
-   File-based email outbox by default; optional SMTP.
-   Streamlit dashboard for run history, products, statuses, incidents,
    coverage, and Gold aggregates.
-   SQL Gold views over normalized rows and the target-hour status
    ledger: hourly coverage, per-keyword unit mix and price spread,
    organic-vs-sponsored rank per product, and quarantine counts.
-   GitHub Actions CI runs the test suite and a mock smoke run on every
    push.

## Requirements

Python 3.10+; no credentials are needed for the mock demo.

## Quick start

### Windows PowerShell

``` powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m pytest -q
python -m src.main --run-once
python -m src.main --demo
python -m streamlit run src/dashboard/app.py
```

If activation is slow or inconvenient, call the environment's
interpreter directly:

``` powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.main --demo
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

### macOS / Linux / WSL

``` bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m pytest -q
python -m src.main --run-once
python -m src.main --demo
python -m streamlit run src/dashboard/app.py
```

Keep real credentials in an untracked `.env`; do not commit secrets.

## Useful commands

  ----------------------------------------------------------------------------------------------------------------
  Goal                                Command
  ----------------------------------- ----------------------------------------------------------------------------
  Run all configured targets once     `python -m src.main --run-once`

  Run one keyword                     `python -m src.main --run-once --keyword "men white sneakers"`

  Backfill a specific hour            `python -m src.main --run-once --hour 2026-10-16T09:00:00+05:30`

  Backfill last N hours               `python -m src.main --backfill-hours 3`

  Start hourly scheduler (foreground) `python -m src.main --schedule`

  Check completeness / process alerts `python -m src.main --check-completeness --hour 2026-10-16T09:00:00+05:30`

  Replay raw snapshots without        `python -m src.main --reload-raw --hour 2026-10-16T09:00:00+05:30`
  refetching                          

  Run missing-slot, alert, backfill,  `python -m src.main --demo`
  recovery demo                       

  Start dashboard                     `python -m streamlit run src/dashboard/app.py`

  Prove same-hour reruns do not       `python scripts/check_idempotency.py` (rows per slot equal distinct
  duplicate rows                      target+rank)

  List quarantined records            `python scripts/show_quarantine.py --details`
  ----------------------------------------------------------------------------------------------------------------

`scheduled_hour` is the intended IST hour, stored as a UTC instant;
`time_stamp` is the actual fetch time. `--hour` accepts an ISO-8601
timestamp and is normalized to the top of its IST hour. For example,
10:00 IST is `04:30Z`.

## Configuration and layout

-   `config/targets.json`: 50 keywords.
-   `config/settings.yaml`: adapter mode, pages, timeouts, retries, rate
    limit, grace period, completeness threshold, and alerts.
-   `.env.example`: environment-variable template, including optional
    SMTP.
-   `config/cron.example`: OS scheduler examples.

Pipeline flow:

``` text
targets/settings -> run ledger + lock -> mock fetch
 -> raw HTML + metadata -> parse -> validate/dedupe -> rank
      (rejected cards/placements/pages -> quarantine_record)
 -> SQLite normalized rows -> completeness -> incident/email -> dashboard
```

  -----------------------------------------------------------------------------------------
  Purpose                             Location
  ----------------------------------- -----------------------------------------------------
  SQLite database/schema              `data/pipeline.db`, `sql/schema.sql`

  Raw snapshots (Bronze-like)         `data/raw/platform=.../date=.../hour=.../<run_id>/`

  Normalized rows (Silver)            SQLite `visibility_product`

  Gold aggregates                     SQL views in `sql/schema.sql` (see `docs/gold_layer.md`)

  Quarantine (rejected records)       SQLite `quarantine_record`, view `gold_quarantine_summary`

  File email outbox                   `data/outbox/*.eml`

  Dashboard                           `src/dashboard/app.py`

  Screenshots                         `screenshots/`
  -----------------------------------------------------------------------------------------

`data/` is generated locally and git-ignored. `--reload-raw` reprocesses
stored snapshots without fetching again. This is a local SQLite
pipeline, not a distributed platform.

## Scheduling, statuses, and alerts

`--schedule` runs APScheduler in the foreground at minute 30 UTC (the
top of each IST hour). Keep the process running for scheduling to
continue. `config/cron.example` also documents OS scheduler
alternatives. A database lock prevents overlapping runs; an overlapping
invocation is recorded as `skipped_overlap`.

Target-hour statuses include `success`, `zero_result`, `partial`,
`parse_failed`, `blocked`, `failed`, `running`, `missing`, and
`not_yet_due`. Only `success` and `zero_result` count as complete.
`partial` means page 1 parsed but a later page failed, either because
it could not be parsed or because its fetch retries were exhausted; the
page-1 rows are kept but the slot is not complete. A status audit test
(`tests/test_status_audit.py`) produces every status from real
behaviour, never from a process exit code.
Missing terminal statuses after the configured grace period are flagged.

The alert system checks conditions including failed runs, missing slots,
low completeness, parser/schema errors, row-count drops, stale data, and
blocked targets. Conditions are aggregated per platform-hour to reduce
alert storms. Repeated checks are deduplicated according to incident
state/cooldown; a healthy backfill can resolve the incident and generate
a recovery email.

-   Default `ALERT_SINK=file`: emails are written to `data/outbox/`.
-   Optional SMTP: configure environment variables in `.env`.
-   Mailpit is optional for local SMTP testing; Docker is not required
    for the default demo.

## Quarantine

Rejected records are stored, not just logged: product cards with no
name or no identity, placements that fail validation, repeated
placements (including pagination drift), and whole pages that failed to
parse or were blocked. A genuine `zero_result` page is not quarantined,
and values that are merely normalised to NULL are not either. Quarantine
never changes a target's status, and its rows can be rebuilt with
`--reload-raw`. Reasons, counts and limits are in
[`docs/quarantine.md`](docs/quarantine.md); the dashboard has a
*Quarantine* tab.

## Recovery

-   Backfill a missing or failed hour, then run completeness evaluation
    again.
-   Raw snapshots are saved before DB loading. After a database failure,
    `--reload-raw --hour <hour>` replays saved files without refetching.
-   Run and target-hour state are persisted so missing slots can be
    detected after the grace period.

This is local persisted run state and raw replay, not
distributed/page-level checkpointing.

## Mock versus live scope

  -----------------------------------------------------------------------
  Area                                Status
  ----------------------------------- -----------------------------------
  Product observations                Synthetic generator and labelled
                                      fixtures

  Automated live AJIO collection      Disabled; adapter fails closed

  Parser                              Tested against mock/fixture
                                      structures, not the live AJIO DOM

  Storage, scheduling, completeness,  Implemented locally and covered by
  alert lifecycle, replay, dashboard  tests
  -----------------------------------------------------------------------

Do not interpret mock-tested politeness behaviour as permission to
collect from prohibited paths.

## Tests and observed verification

Run:

``` bash
python -m pytest -q
```

The suite now has 94 tests. A clean-clone run made before the quarantine
layer was added (86 tests) completed with **86 passed in 375.12
seconds**; on a fast machine the suite takes a few seconds, so that
duration was not investigated further. GitHub Actions runs `pytest` and
a mock smoke run on every push. The mock demo also completed
successfully: 50 targets per slot, 48
`success`, 2 `zero_result`, 1,616 rows written/upserted per slot,
missing-slot detection, repeated-alert aggregation, late backfill, 100%
completeness, and incident resolution. These are mock-environment
results, not live AJIO observations.

See [`docs/curveballs.md`](docs/curveballs.md),
[`KNOWN_GAPS.md`](KNOWN_GAPS.md), and
[`docs/evidence_checklist.md`](docs/evidence_checklist.md). Capture your
own screenshots in `screenshots/`; do not include credentials or private
information.
