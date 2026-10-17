# Decisions

Each answer gives the choice, one rejected alternative, and why. All data is mock (see README); where a choice depends on how the real site behaves, that is said.

## 1. How is each `product_type` identified?
**Chose:** an explicit placement marker on each result card (`data-kind` = `SB` / `SP` / otherwise Organic), plus `campaign_id` only when the card carries one. A banner (`SB`) may legitimately have no product id or price. Unknown or missing markers fall back to Organic *only in this mock parser*. **Rejected:** inferring ads from position, price or product title, because that invents sponsorship data. **Why:** type must come from evidence on the page. On real AJIO the marker is unverified (the ad script `jioAds.js` was seen but not inspected, and live collection is not permitted), so a live parser would have to be built from documented, permitted evidence.

## 2. Idempotency / deduplication key, and what happens when an hour runs twice
**Chose:** a row is keyed by `(platform, target_id, scheduled_hour, absolute_rank)`, written with an upsert. After a complete parse, rows beyond the new last rank are deleted; after a partial or failed parse, nothing is deleted. Within a run, a repeated placement is dropped using `(product_type, product_id or URL path, campaign_id for paid units)`, never the title; the same product as SP and Organic stays as two rows. `product_id` comes from the canonical `/p/<id>` URL path with tracking parameters stripped. **Rejected:** append-only inserts with a `run_id` in the key, which would duplicate the hour on every rerun and make "the current state of this slot" hard to query. **Why:** reruns and backfills must converge to one answer. The trade-off: the table holds the latest view of each slot, while history of attempts lives in the raw snapshots and the run ledger.

## 3. How is a genuine zero-result slot told apart from a failed one?
**Chose:** `zero_result` requires a present grid, no cards and a non-empty explicit no-results marker. A missing or renamed grid, an empty grid with no marker, or cards that all fail validation is `parse_failed`; a 403, 429 past its budget or challenge page is `blocked`; exhausted retries are `failed`. Only `success` and `zero_result` count as complete, and a layout change writes no rows. **Rejected:** treating "zero parsed cards" as zero results, which would turn every layout change into a quiet outage. **Why:** the two must be different states with different alerts.

## 4. Which hour does a row belong to?
**Chose:** `scheduled_hour`, the **IST hour** the run was scheduled for (top of the Asia/Kolkata hour), stored as a UTC instant: 10:00 IST is `2026-10-16T04:30:00Z`. It is fixed once when the run starts and written to every row, status and run, whatever the clock says later. `time_stamp` stays the real fetch time. A run scheduled for 10:00 IST that starts at 10:59:58 and finishes at 11:00:40 still lands in the 10:00 IST slot; a backfill writes to the requested hour. Alert emails and the dashboard show both IST and UTC. **Rejected:** bucketing by fetch time, which moves late runs into the wrong hour and makes backfills impossible. **Rejected (second alternative):** UTC hour slots. They are simpler, but IST is UTC+5:30, so a UTC slot would show as 10:30 IST and the brief's "10:00 IST run" would land in a slot that is not 10:00 IST. **Known limit:** the slot offset (+05:30) is a constant in `src/timeutil.py`, not a setting; cron must fire at minute 30 on a UTC clock (see `config/cron.example`).

## 5. Curveballs handled
| ID | Result | Notes |
|---|---|---|
| I-1 silent layout change | **Full** | `parse_failed`, raw kept, alert, no rows |
| I-2 genuine zero results | **Full** | `zero_result`, counted complete, no alert |
| I-3 mixed placements | **Full** | ranks match the worked example; `campaign_id` only if present |
| I-4 pagination drift | **Partial** | repeated placement detected, first occurrence kept, anomaly stored and logged; a product that appears on *neither* page cannot be detected without an independent count |
| I-5 messy values | **Full** | exact decimals, `1.2K` -> 1200, missing = NULL, banners parse |
| I-6 same product twice | **Full** | SP and Organic kept separately; tracking-parameter duplicates removed by product key |
| I-7 throttled/blocked | **Full (mock)** | 429 waits per `Retry-After` within a budget; 403/challenge stops the target, marks `blocked`, alerts; no evasion |
| I-8 hour boundary | **Full (IST slots)** | see Q4 |
| I-9 overlapping runs | **Full** | lock; second run recorded as `skipped_overlap`; slot shows missing |
| I-10 late backfill | **Full** | rows carry the old slot, no duplicates, incident resolved, one recovery email |
| I-11 database down mid-run | **Full for mid-run** | raw + sidecar on disk first; failures contained per target; `--reload-raw` loads without refetching. If the database is down *before* a run starts, the run refuses to start (nothing fetched, nothing lost) |
| I-12 alert storm | **Full** | one incident and email per hour; resend only on trigger-set change or cooldown |

Every claimed scenario has a fixture or simulated response and an automated test; the tests were mutation-checked (removing each behaviour made a test fail). Map: `docs/curveballs.md`.

## 6. What breaks first at 100x targets (5,000 keywords)?
**First:** the single-process, sequential fetch loop. At 0.5 requests/s, 10,000 requests need over 5 hours, so an hourly run cannot finish; politeness, not CPU, is the limit. **Next:** SQLite's single writer and the one platform-wide lock. **Chose to defer:** I would move to PostgreSQL, shard targets across workers with per-source concurrency and rate limits, and use per-target leases instead of one global lock. **Rejected now:** building this early, since it cannot be tested honestly against a mock. Raw snapshots would move to object storage with retention, and the dashboard grid would need aggregation instead of one cell per target-hour.
