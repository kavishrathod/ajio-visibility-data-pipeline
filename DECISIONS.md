# Engineering Decisions

> **Scope:** product observations are synthetic or fixture-based.
> Automated live AJIO collection is disabled because the project's
> source research found the relevant search/API paths disallowed. Live
> DOM behaviour is not claimed as verified.

Mapping to the brief's six questions: 1 = section 1, 2 = section 2, 3 = section 3,
4 = section 4, 5 = section 9 (curveballs), 6 = section 10 (100x). Sections 5 to 8 and
11 record further decisions.

## 1. Placement type

**Chosen:** use an explicit mock-card marker (`data-kind`) for `SB` and
`SP`; otherwise classify as Organic. Preserve `campaign_id` when
present. A sponsored-brand banner may not have a product ID or price.

**Rejected:** infer sponsorship from rank, price, or title, because
these do not prove a placement is sponsored.

**Trade-off:** markers are verified against mock/fixture structure only;
the live AJIO DOM has not been validated.

**What was actually observed:** the search page embeds a schema.org JSON-LD
`ItemList` (name, image, URL, position, `numberOfItems`). It has no price and no
sponsored marker, so it cannot decide a placement type. The mock pages carry that
layer for product identity and put price, rating and placement on simulated cards.

**Rejected:** treating the JSON-LD as proof that a page is healthy. A page with
JSON-LD but no product grid is `parse_failed`, because price and placement exist
only in the grid. A disagreement between the two (different product at a position,
different counts) is logged as a parser warning and the JSON-LD is not trusted for
that card.

## 2. Idempotency and deduplication

**Chosen:** upsert normalized rows using
`(platform, target_id, scheduled_hour, absolute_rank)`. Within a run,
deduplicate by placement type plus product identity (`product_id` or URL
identity) and campaign identity for paid placements. The same product
appearing as SP and Organic remains two placements.

**Rejected:** append-only inserts keyed by `run_id`, which would
duplicate the current slot on reruns.

**Reason:** reruns/backfills should converge to one current view per
target-hour. Raw snapshots and the run ledger retain attempt history.
Complete parses can remove stale ranks; partial/failed parses must not
erase previously valid rows.

## 3. Zero results versus failure

**Chosen:** `zero_result` requires an explicit no-results marker and a
present result grid with no cards. Missing/renamed structure, empty grid
without a marker, or records failing validation are parser failures.
403/challenge or 429 beyond its retry budget is blocked; exhausted
retries are failed.

**Rejected:** treat every parse with zero cards as a legitimate
zero-result search.

**Partial:** if page 1 parsed and a later page fails, either by a parse failure
or because its fetch retries are exhausted, the target is `partial`. The page-1
rows are kept, the slot is not complete, and earlier good rows are never erased.
Before a status audit, an exhausted fetch on page 2 was recorded as `failed`
even though page 1 had been saved. Rejected records and whole failed pages are
kept in the quarantine layer (section 11).

**Reason:** layout changes and blocks must not look like healthy
searches. Only `success` and `zero_result` count as complete.

## 4. Hour assignment

**Chosen:** fix `scheduled_hour` to the intended IST hour at run start
and store it as a UTC instant. `time_stamp` is the actual fetch time.
Backfills use the requested old slot.

**Rejected:** assign rows based on completion time, which can move late
runs into the wrong hour.

**Also rejected:** UTC hour slots. They are simpler, but IST is UTC+5:30, so a
UTC slot would display as 10:30 IST and the brief's "10:00 IST run" would not land
in a 10:00 IST slot. Slots are floored to the IST hour and stored as UTC instants
(10:00 IST is `04:30Z`), so storage and comparison stay unambiguous.

**Reason:** completeness and backfills need consistent slot identity.
The scheduler fires at minute 30 UTC to align with IST hours. The IST
offset is currently a code constant, not a dynamic setting.

## 5. Raw-first storage and replay

**Chosen:** write raw HTML and metadata sidecars before database
loading. `--reload-raw --hour <hour>` reprocesses saved snapshots
without refetching.

**Rejected:** retain only parsed rows or fetch again after a database
failure.

**Reason:** raw evidence supports debugging and replay while preserving
original fetch timestamps. This is a local replay mechanism, not
distributed checkpointing.

## 6. Local architecture

**Chosen:** SQLite, a database overlap lock, APScheduler, and SQL views
for Gold aggregates.

**Rejected:** add distributed workers, a separate orchestration service,
or a production warehouse before the local assessment flow is validated.

**Reason:** this is a local-first mock assessment. The sequential
collector, SQLite single-writer behaviour, and global lock are scope
limits.

**Gold as views, not tables:** `gold_hour_summary`, `gold_keyword_hour`,
`gold_product_placement` and `gold_quarantine_summary` are SQL views. They always
agree with the normalized rows and the status ledger, and a rerun or backfill
cannot create duplicate aggregates. The cost is recomputation on every read, which
is negligible here. GitHub Actions runs the tests and a smoke run on each push.

## 7. Alert lifecycle

**Chosen:** persist incidents per platform-hour, aggregate active
conditions, deduplicate repeat notifications according to incident
state/cooldown, and send a recovery notification when the slot becomes
healthy.

**Rejected:** send one email per failed keyword or send another email on
every repeated check.

**Reason:** aggregation reduces alert storms. The demo exercised a
missing-hour alert, repeated-check aggregation, late backfill, 100%
completeness, and incident resolution/recovery state.

## 8. Respect source restrictions

**Chosen:** disable live AJIO collection and clearly label synthetic
data.

**Rejected:** stealth, proxies, CAPTCHA bypass, private endpoints, or
other ways of evading access restrictions.

**Reason:** demonstrate pipeline engineering without misrepresenting
synthetic observations or bypassing restrictions.

## 9. Curveball scenarios and limitations

  -----------------------------------------------------------------------
  Scenario                Behaviour covered       Limitation
  ----------------------- ----------------------- -----------------------
  Silent layout change    `parse_failed`;         Live AJIO DOM not
                          preserve raw; do not    tested
                          report zero results     

  Genuine zero results    Explicit marker becomes Depends on mock/fixture
                          `zero_result`           contract

  Mixed placements        Separate SB, SP,        Real-site markers
                          Organic rows and ranks  unverified

  Pagination              Duplicate detection and Items absent from all
  overlap/drift           anomaly logging         returned pages cannot
                                                  be inferred without an
                                                  independent count

  Messy values            Parse supported         Limited to mock/fixture
                          price/rating/count      formats
                          formats and nulls       

  Same product twice      Remove duplicate        Identity depends on
                          placement; preserve     product ID/URL
                          different placement     availability
                          types                   

  Throttling/blocking     Bounded `Retry-After`;  Exercised through
                          stop on 403/challenge   mocks, not live AJIO
                                                  requests

  Hour boundary           Keep scheduled slot     IST offset is a code
                          fixed                   constant

  Overlapping runs        Lock; second run skips  Local single-process
                          fetching                architecture

  Late backfill           Idempotent old-slot     Requires retained
                          load and incident       raw/config
                          recovery                

  DB failure mid-load     Raw-first persistence   DB unavailable before
                          and replay              start prevents run
                                                  startup

  Alert storm             Aggregate triggers per  Email delivery depends
                          platform-hour           on local configuration
  -----------------------------------------------------------------------

The scenario-to-test map is in
[`docs/curveballs.md`](docs/curveballs.md).

## 10. What would break first at 100× scale?

**First bottleneck:** sequential collection under conservative
per-source rate limits. At 0.5 requests/second, 10,000 requests require
over five hours before response overhead.

**Next:** SQLite's single writer, one platform-wide lock, and a large
coverage grid.

**Also at scale:** the quarantine table grows with every rejected record and has no
retention yet, and the Gold views would need to be materialised per hour.

**Possible future design:** PostgreSQL, workers with per-source rate
limits and per-target leases, object storage with retention, and
aggregated dashboard queries. These are deferred because the current
assessment is local and mock-first.

## 11. Quarantine of rejected records

**Chosen:** store every record or page rejected on the way to the normalized table
in `quarantine_record`: unparseable cards (`card_missing_name`,
`card_missing_identity`), placements failing validation, repeated placements
(`duplicate_placement`, `cross_page_duplicate`), and whole pages that failed to
parse or were blocked (`page_parse_failed`, `page_blocked`). Each row keeps the
reason, the payload, and the path of the raw page. Rows are append-only per run
(`INSERT OR IGNORE` on a unique key); `gold_quarantine_summary` counts the latest
attempt per target-hour only.

**Rejected:** (a) log-only rejection, which loses the evidence and cannot be
queried; (b) overwrite quarantine rows on a rerun, which erases the history of
earlier attempts; (c) failing the target when a quarantine write fails.

**Reason:** a silently dropped record is indistinguishable from a record that never
existed, and the brief asks for invalid data to be detected rather than hidden.
Quarantine is evidence, not a dependency: a failed write is reported in the run's
`db_errors` but never changes a status, and `--reload-raw` rebuilds the rows from
the raw pages.

**Not quarantined:** a genuine `zero_result` (healthy), and values normalised to
NULL (the record is valid). Not built: an alert on a high quarantine rate, and a
release or reprocess workflow. See `docs/quarantine.md`.

