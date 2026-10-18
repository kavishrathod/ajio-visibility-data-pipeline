# Known gaps and honest scope

1. **Mock source only.** No live AJIO search is requested: robots.txt disallows `/search` and `/api/*`. The live adapter fails closed. Nothing here is a real AJIO observation, and prices, ranks, ratings, sponsorship labels and campaign ids are synthetic.

2. **Parser contract is half-observed.** The JSON-LD `ItemList` layer (name, image, url, position, numberOfItems) mirrors what I saw in AJIO's page source. The grid layer (`product-grid`, `product-card`, `data-*` attributes carrying price, rating, placement) is simulated: I did not inspect AJIO's rendered DOM and did not verify how AJIO marks sponsored units. JSON-LD positions in the mock restart at 1 on each page; whether AJIO's continue across pages is unverified.

3. **I-4 is partial.** A placement repeated across pages is detected and handled; a product that disappears from both pages is not detectable without an independent total.

4. **Fixed IST slots.** Slots are IST hours (UTC+05:30) stored as UTC instants. The offset is a constant in `src/timeutil.py`, not a configuration setting, and IST has no daylight saving so no DST handling exists. Cron on a UTC machine must fire at minute 30.

5. **Database is a single point of failure for alerting.** Incidents are stored in the same SQLite file. If the database is down before a run starts, the run refuses to start and no incident can be written; production needs an external heartbeat/watchdog. Mid-run outages are handled (raw files kept, `--reload-raw`).

6. **Single host.** SQLite and one lock row suit a demo. The lock expires after 4 hours, or immediately when its run is marked finished. There is no heartbeat/lease for a hung process.

7. **Scheduler is foreground or external.** `--schedule` stops if the process stops; stale-data detection only fires when a check runs (the cron example runs one at minute 20). Missed hours are found by the completeness check and backfilled by hand.

8. **Baselines are simple.** Row-drop uses a rolling median of recent comparable runs, with no seasonality and a minimum of three runs.

9. **SMTP is tested with a stand-in.** Tests cover credentials-from-environment, failure handling and the file sink. I did not verify delivery to a live Mailpit or SMTP server.

10. **Live pacing untested.** The rate limiter and backoff are unit-tested with fake clocks and apply to non-mock adapters; they were never run against a real server (and must not be without permission).

11. **Not done:** Docker Compose, a rank-movement report, and a data contract (optional stretch items). Property-based tests and a scaling note are included.

12. **Quarantine is evidence, not a workflow.** Rows are stored and reported, but there is no alert on a high quarantine rate, no retention or purge, and no release or reprocess step for a single record (replay is per hour via `--reload-raw`). A fetch that never returned a page has nothing to quarantine and shows only as `failed` or `partial`. Values normalised to NULL are not quarantined.

13. **Gold is views, not materialised tables.** They are recomputed on every read, which is fine at this scale and the first thing to change at 100x. Brand-level organic-versus-sponsored comparison is not built (the output record has no brand field); the comparison is per product id. Rank-movement reporting is not built.

14. **Test duration.** The clean-clone runs on my Windows machine took 375.12 seconds (86 tests), 470.30 seconds (94 tests) and 518.33 seconds (113 tests). I have not investigated why. With dependency installation and the demo added, a fresh setup on a similar machine may take longer than 10 minutes. The 35 tests that write no files run in a few seconds (command in the README).

15. **CI is basic.** One workflow runs `pytest` on Python 3.11 and 3.12 plus a mock smoke run. No linting, coverage or dependency pinning.

16. **Lenient value parsing.** `parse_price` ignores an exponent (`1e5` reads as `1.00`) and strips any comma (`12,34` reads as `1234.00`). Real prices use neither, and the property tests document it, but it is not rejected.

17. **Infinite scroll is not modelled.** The live search page loads results by infinite scroll in a logged-out session; the mock serves numbered pages (page 1, page 2) per keyword. How a real source would be paged was not established.
