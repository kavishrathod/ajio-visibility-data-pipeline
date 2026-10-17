# Scaling note: 20,000 targets

A design sketch, not implemented. Today: 50 keywords x 2 pages, one process, SQLite, one global lock. A local
run of 100 pages takes about 14 seconds including database writes (no network), so about 0.14 s of CPU per page.
Live collection from AJIO is disabled here (`robots.txt` disallows `/search`); this note assumes a permitted
source, such as an agreed rate or a licensed feed.

## 1. Load
- **Requests:** 20,000 targets x 2 pages = 40,000 pages per hour = **11.1 requests/s sustained** (12.2 with 10% retries).
- **Rows:** about 32 per target (1,616 per 50 keywords today) = ~650,000 rows/hour, 15.5 M/day, ~465 M per 30 days.
- **Raw pages:** ~960,000 per day. At an assumed 30 KB gzipped each (not measured) that is ~29 GB/day, ~0.9 TB per 30 days.

## 2. Politeness is the binding limit, not compute
| Rate agreed with the source | Pages/hour | Targets refreshed hourly (2 pages) | Time to cover all 20,000 |
|---|---|---|---|
| 0.5 req/s (today's setting) | 1,800 | 900 | 22 h |
| 2 req/s | 7,200 | 3,600 | 5.6 h |
| 5 req/s | 18,000 | 9,000 | 2.2 h |
| 12 req/s | 43,200 | 21,600 | 0.9 h |

Hourly coverage of all 20,000 needs about 12 req/s, which is not acceptable without the source's agreement.
Otherwise tier the targets: a hot set hourly, the long tail every 6 to 12 hours, sized to the rate budget.
- One **shared token bucket** per source, sized to the agreed rate and split across shards; requests spread with
  jitter across the hour instead of a burst at :00.
- Honour `Retry-After`. A **circuit breaker** per shard: repeated 429s halve its rate; a 403 or challenge stops the
  shard and alerts. No proxies, CAPTCHA solving or stealth, as now.

## 3. Partitioning
- **Work:** `hash(target_id) mod 64` logical shards, stable across hours. Tasks are `(target_id, scheduled_hour)`.
- **Silver, status and quarantine tables (PostgreSQL):** range-partitioned by `scheduled_hour` (daily or monthly).
  The current unique key already contains `scheduled_hour`, so it carries over. Expire data by dropping partitions,
  not by `DELETE`. Quarantine gets a 30-day retention and a payload size cap.
- **Bronze (object storage):** `platform=/date=/hour=/shard=/run_id/`, gzipped; hot for 7 days, kept 30, then thinned.
- **Gold:** the SQL views become hourly incremental materialised tables.

## 4. Concurrency
- A **queue** (PostgreSQL `FOR UPDATE SKIP LOCKED`, or SQS) feeds a worker pool. The single global lock becomes a
  **per-task lease** with a timeout and heartbeat, so a hung worker loses its task rather than blocking the platform.
- Upserts are idempotent, so at-least-once delivery and retries are safe. This is already tested for reruns.
- Fetching is I/O bound: 12 req/s x ~2 s is ~24 requests in flight, and parsing needs ~1.6 cores in total, so
  **4 to 6 small workers** are enough. Raw pages are written before any database write, as now.
- Completeness is an anti-join of expected `(target, hour)` slots against statuses. Alerts stay one incident per
  platform-hour, with a per-shard breakdown, so a whole failed shard is still one email.
- The dashboard's target x hour grid (480,000 cells a day) becomes a shard x hour heatmap with drill-down.

## 5. Rough monthly cost (order of magnitude, +/-2x, list prices not checked)
| Item | Sizing | Estimate |
|---|---|---|
| Workers | 4 to 6 x 2 vCPU | $150 to 300 |
| Managed PostgreSQL | ~200 GB Silver per 30 days plus indexes, 4 to 8 vCPU | $400 to 900 |
| Object storage | ~0.9 TB raw, lifecycle rules | $20 to 40 |
| Queue, logs, metrics, alerting | | $50 to 150 |
| **Infrastructure total** | | **about $650 to 1,500** |

The largest unknown is not in this table: what access to the source costs (agreement or licence).

## 6. What breaks first
1. The source's rate budget. 2. SQLite's single writer. 3. The sequential loop and the global lock.
4. The coverage grid. 5. Unbounded quarantine and recomputed Gold views. 6. Email volume, already aggregated.
