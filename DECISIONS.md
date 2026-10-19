# DECISIONS.md

## 1. Identifying product types on AJIO

**Choice:** I use placement labels in mock pages to distinguish Sponsored Brand (SB), Sponsored Product (SP), and Organic results. Product type is stored separately from rank because position alone does not prove that a result is sponsored. Brands come from an explicit field, not title inference. The pipeline stores a cleaned `brand` and normalized `brand_key`; aliases such as "U.S. Polo Assn." and "US Polo Assn." are maintained in `config/brand_aliases.json`. Missing brands remain NULL and are excluded from brand comparisons.

**Alternative rejected:** Inferring sponsorship from rank or product position, because it can misclassify organic results.

**Reason and limitation:** Explicit labels reduce ambiguity. The automated pipeline uses mock data; live AJIO placement markers have not been verified.

## 2. Idempotency and deduplication

**Choice:** A placement is identified using the available product ID or URL, scheduled hour, keyword, and placement information. Upserts and duplicate checks allow a scheduled hour to be rerun without duplicating normalized placements. Rejected duplicates are recorded in quarantine as `duplicate_placement` or `cross_page_duplicate`. Raw evidence and run history are retained separately.

Duplicate spikes are flagged when an hour has at least 10 duplicates, duplicates represent at least 2% of units, and the rate is at least five times the rolling median of previous complete hours, once three are available. These thresholds are defaults, not tuned on real AJIO data. See `docs/duplicate_spike.md`.

**Alternative rejected:** Appending every row on each run, because retries and backfills would inflate counts.

**Reason:** Idempotency protects hourly comparisons and keeps rejected records auditable. Matching is less reliable when neither a usable product ID nor URL exists.

## 3. Genuine zero results versus a failed slot

**Choice:** A slot is `zero_result` only when an explicit no-results indicator is present. An empty or unusable page is not automatically considered empty; parsing failures, blocking, request failures, and partial pagination have separate outcomes. If page 1 succeeds but a later page fails, page-1 rows are retained and the slot is marked `partial`, not complete. Rejected pages can be retained in quarantine.

**Alternative rejected:** Treating an empty product list as proof that no products exist.

**Reason:** A blocked request or changed page layout must not appear as a genuine drop in visibility. These rules are tested against mock pages and fixtures; live AJIO behaviour remains unverified.

## 4. Assigning rows to an hour

**Choice:** Rows belong to the scheduled collection hour, not the time a request finishes. Slots use IST, and scheduled-hour timestamps are stored as UTC instants. Late requests and backfills therefore remain associated with the intended slot.

**Alternative rejected:** Assigning rows to individual request-completion times, which could scatter one scheduled collection across different hourly buckets.

**Reason:** Consistent slot assignment supports reliable coverage and hourly comparisons. The current time utility uses a fixed IST offset rather than a configurable timezone implementation.

## 5. Curveballs: fully handled, partially handled, or skipped

**Choice:** I prioritised failure scenarios that could silently corrupt the data or make monitoring misleading. These classifications describe tested mock/fixture behaviour, not verification against live AJIO.

- **I-1 — Silent layout change: Full (fixtures).** Parser failures are distinguished from genuine zero results.
- **I-2 — Genuine zero results: Full.** An explicit no-results indicator distinguishes empty results from parsing failures.
- **I-3 — Mixed placement types: Full.** Sponsored and organic placements remain distinct, including when the same product appears in both.
- **I-4 — Pagination drift: Partial.** Cross-page duplicates are detected and quarantined, but missing products cannot be identified without an independent expected total.
- **I-5 — Messy values: Full (tested inputs).** Invalid values are handled. Property-based tests exposed rating-parsing and product-key bugs that were fixed.
- **I-6 — Same product twice: Full.** Duplicate placements are detected while different placement types remain distinct.
- **I-7 — Throttled and blocked: Full (mock).** Simulated throttling and blocking are handled; live AJIO behaviour is unverified.
- **I-8 — Hour boundary: Full (IST slots).** Rows use their scheduled collection hour.
- **I-9 — Overlapping runs: Full.** The tested global lock rejects overlapping runs.
- **I-10 — Late backfill: Full.** The tested backfill flow processes a previously missing slot.
- **I-11 — Database down mid-run: Full (tested scenario).** The documented mid-run failure behaviour is tested, not every production failure mode.
- **I-12 — Alert storm: Full.** Failures are aggregated, with incident deduplication, cooldown, and recovery behaviour tested.

**Not implemented or not fully verified:** Live AJIO collection, production-scale scheduling, complete quarantine reprocessing, quarantine retention/purge policies, and high-volume quarantine alerts. I did not bypass source restrictions to test live collection.

**Alternative rejected:** Claiming every curveball was solved because tests passed.

**Reason:** Fixture tests demonstrate only the behaviour they exercise. Clear limits keep failures and unverified assumptions visible.

## 6. What would break first at 100× the number of targets?

**Choice:** I kept the project local-first, using SQLite, a single-host overlap lock, raw snapshots, and a local scheduler. This keeps the assessment reproducible without unnecessary infrastructure.

**Alternative rejected:** Adding distributed infrastructure before validating the core collection, data-quality, and recovery behaviour.

**Reason:** Collection time and request volume would likely become the first constraints. At 100× scale, a single process might miss hourly deadlines; SQLite writes, dashboard queries, and the single-host lock could also become bottlenecks. Uncontrolled concurrency could exceed acceptable request rates.

**Worked example:** `docs/scaling_note.md` estimates 20,000 targets at two pages each as 40,000 pages per hour, or about 11 requests per second. Source rate limits may constrain throughput before compute does. These are estimates based on stated assumptions, not measured production results.

**Next step:** Measure runtime and database load, then introduce durable work distribution, bounded workers, coordinated rate limits, and a database suited to concurrent workloads if measurements justify them. Partition raw data by scheduled hour and monitor queue lag, failed targets, and slot completeness.
