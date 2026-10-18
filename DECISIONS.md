# DECISIONS.md

## 1. Identifying product types on AJIO

**Choice:** I used the placement labels available in my mock pages to distinguish Sponsored Brand (SB), Sponsored Product (SP), and Organic results. I store the product type separately from the rank so that sponsored and organic placements are not treated as the same type of result. I also inspected the page source and embedded JSON-LD during source research, but JSON-LD alone was not sufficient evidence to identify every placement type.

Brands follow the same rule. The live page shows a brand label under each product, so the mock cards carry an explicit brand field, and the pipeline stores a cleaned `brand` and a normalized `brand_key`. I never infer a brand from the product title, because title prefixes do not follow one rule; a card without a brand label has a NULL brand and is left out of the brand comparison, and the share of units with a brand is reported. Variants that differ only in case, spacing or Unicode share a key, and any other equivalence (for example "U.S. Polo Assn." and "US Polo Assn") is a hand-curated entry in `config/brand_aliases.json`.

**Alternative rejected:** I rejected inferring product type from rank or product position alone because an item appearing first does not prove that it is sponsored.

**Limitation:** My automated pipeline uses labelled mock data. I did not verify the live AJIO rendered DOM or establish that its actual sponsored-placement markers follow the same contract. I therefore do not claim that the pipeline is collecting verified live AJIO placements.

## 2. Idempotency and deduplication

**Choice:** I use a stable product identity, based on the available product ID or URL, together with the scheduled hour, keyword, and placement information to identify a placement. Repeated placements are detected, while different placement types for the same product can remain distinct. Database upserts and duplicate checks allow the same scheduled hour to be processed again without simply appending another copy of every row. Duplicates that are dropped are not lost: they are written to the quarantine table with a reason (`duplicate_placement` on the same page, `cross_page_duplicate` across pages).

**Alternative rejected:** I rejected inserting every collected row as a new record because retries, backfills, and rerunning an hour would inflate counts and corrupt the results.

**What happens on a rerun:** The pipeline can process the same hour again without duplicating the same placements. Raw collection evidence and run history are retained separately from the normalized results, so a rerun does not mean that all evidence of the earlier attempt is discarded.

**Duplicate spikes:** each target-hour records how many repeated placements it dropped (`duplicate_count`). An hour is a spike when it has at least 10 duplicates, they are at least 2% of the units seen, and that rate is at least 5 times the rolling median of the previous complete hours (used once three exist). I chose a count floor and a rate floor because a few repeats are normal and a tiny hour could otherwise reach a high rate; I added the baseline so a stable duplicate rate does not alert every hour. The defaults are my own and have not been tuned on real data. A spike opens an incident like the other triggers (aggregated, cooldown, one recovery); details are in `docs/duplicate_spike.md`.

**Limitation:** Deduplication depends on having a usable product identity. If a product has neither a reliable ID nor a usable URL, identity matching becomes less reliable.

## 3. Genuine zero results versus a failed slot

**Choice:** I distinguish `zero_result` from collection and parsing failures. A slot is considered a genuine zero-result slot only when the expected no-results indicator is present. A page that returns successfully but contains no usable product information is not automatically treated as empty; it can be marked `parse_failed`. Blocking, request failures, and partial pagination have separate outcomes. If page 1 parses and a later page fails, either because it cannot be parsed or because its fetch retries are exhausted, the slot is `partial`: the page-1 rows are kept and the slot does not count as complete. While auditing the statuses I found that an exhausted fetch on page 2 had been recorded as `failed` even though page 1 was saved, and I changed it. Pages that failed to parse or were blocked are also kept in quarantine.

**Alternative rejected:** I rejected treating an empty product list as proof that no products exist because an incomplete page, changed layout, or blocked request could produce the same symptom.

**Why it matters:** This distinction prevents a collection failure from appearing as a legitimate drop in product visibility. I retain raw evidence where available so that parsing or loading issues can be investigated and, where supported, replayed.

**Limitation:** The no-results and parsing rules are tested against mock pages and fixtures. Live AJIO page behaviour has not been verified.

## 4. Assigning rows to an hour

**Choice:** I assign rows to the **scheduled collection hour**, rather than the exact time when a request finishes. Slots are defined using IST, while the stored scheduled-hour timestamp is represented as a UTC instant. This keeps results from the same scheduled slot together even if a request finishes late or the slot is backfilled later.

**Alternative rejected:** I rejected assigning each row to its individual collection timestamp because slow requests and retries could spread one scheduled collection across different hourly buckets, making coverage and comparisons inconsistent.

**Limitation:** The current implementation uses a fixed IST offset in its time utility rather than a fully configurable timezone implementation. The scheduling and timestamp conversion should be reviewed if the deployment timezone or scheduling requirements change.

## 5. Curveballs: fully handled, partially handled, or skipped

**Choice:** I prioritised failure scenarios that could silently corrupt the data or make monitoring misleading.

- **Handled in the mock/tested implementation:** Re-running an hour without duplicating normalized placements; distinguishing explicit zero results from failures; detecting missing scheduled slots; aggregating repeated alerts and recording recovery; and quarantining rejected records with reasons rather than silently treating them as valid data.
- **Checked with generated inputs:** property-based tests for price, count and rating parsing, the product key, deduplication and rank continuity across pages. They found two parser bugs that my example-based tests had missed: an out-of-range rating such as `7.5` was read as `5.0`, and a URL whose title slug was `p` produced the wrong product key. I fixed both.
- **Partially handled:** Unusable pages, malformed values, pagination overlap, later-page failures, throttling/blocking, and database recovery have handling and test coverage, but the tests use fixtures or mocked behaviour rather than live AJIO requests. Pagination checks cannot detect a product missing from every returned page when there is no independent expected total.
- **Not implemented or not fully verified:** Live AJIO collection, production-scale scheduling, a complete quarantine reprocessing workflow, quarantine retention/purge policies, and high-volume quarantine alerts. I did not attempt to bypass source restrictions to test live collection.

**Alternative rejected:** I rejected treating every curveball as successfully solved just because a test run passed. A passing fixture test demonstrates the tested behaviour, not that the same behaviour has been verified against a live source or production infrastructure.

**Why:** I wanted failures to remain visible and documented, rather than hide uncertainty behind a success status.

## 6. What would break first at 100× the number of targets?

**Choice:** I kept the current implementation local-first, using SQLite, a single-host overlap lock, raw snapshots, and a scheduler that runs on the same environment. This keeps the assessment reproducible and avoids introducing infrastructure that the current workload does not require.

**Alternative rejected:** I rejected adding distributed infrastructure solely to make the project look production-scale before validating the core collection, data-quality, and recovery behaviour.

**What would break first:** At 100× the target count, collection time and request volume would increase first. A single process could struggle to finish within the hourly window, while SQLite writes, the single-host lock, and dashboard queries could become bottlenecks. Increasing concurrency without coordinated rate limits could also create excessive request traffic or make overlapping runs harder to control.

**Worked example:** `docs/scaling_note.md` works through 20,000 targets. At two pages each that is about 40,000 pages an hour, roughly 11 requests per second, so the rate the source would accept is the first limit, before compute. The same note covers sharding, hour partitioning, per-task leases and a rough monthly cost (order-of-magnitude estimates from stated assumptions). The quarantine table would also need a retention policy, and the Gold views would need to be materialised per hour.

**Next step:** I would measure runtime and database load, then move scheduling and work distribution to a durable queue, use bounded workers with coordinated rate limits, and consider a database designed for concurrent workloads. I would partition raw data by scheduled hour and make monitoring track queue lag, failed targets, and slot completeness. I would scale based on measured bottlenecks rather than simply increasing concurrency.
