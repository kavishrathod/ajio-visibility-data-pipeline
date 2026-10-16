# Known gaps and honest scope

1. **Mock source only.** No live AJIO search is requested: robots.txt disallows `/search` and `/api/*`. The live adapter fails closed. Nothing here is a real AJIO observation, and prices, ranks, ratings, sponsorship labels and campaign ids are synthetic.
2. **Parser contract is mock-specific.** It covers the fixture/generator structure (`product-grid`, `product-card`, `data-*` attributes), not AJIO's real DOM, and I did not verify how AJIO marks sponsored units.
3. **I-4 is partial.** A placement repeated across pages is detected and handled; a product that disappears from both pages is not detectable without an independent total.
4. **UTC slots.** IST hours do not align with UTC hour slots (half-hour offset); emails show both. A configurable slot offset is not implemented.
5. **Database is a single point of failure for alerting.** Incidents are stored in the same SQLite file. If the database is down before a run starts, the run refuses to start and no incident can be written; production needs an external heartbeat/watchdog. Mid-run outages are handled (raw files kept, `--reload-raw`).
6. **Single host.** SQLite and one lock row suit a demo. The lock expires after 4 hours, or immediately when its run is marked finished. There is no heartbeat/lease for a hung process.
7. **Scheduler is foreground or external.** `--schedule` stops if the process stops; stale-data detection only fires when a check runs (the cron example runs one at minute 20). Missed hours are found by the completeness check and backfilled by hand.
8. **Baselines are simple.** Row-drop uses a rolling median of recent comparable runs, with no seasonality and a minimum of three runs.
9. **SMTP is tested with a stand-in.** Tests cover credentials-from-environment, failure handling and the file sink. I did not verify delivery to a live Mailpit in this build; do that and capture the email screenshot.
10. **Live pacing untested.** The rate limiter and backoff are unit-tested with fake clocks and apply to non-mock adapters; they were never run against a real server (and must not be without permission).
11. **Dashboard** is smoke-tested only (it loads and renders against real tables). On very new Streamlit versions `use_container_width` prints a deprecation warning.
12. **Not done:** property-based tests, Docker Compose, scaling note, rank-movement report (optional stretch items).
13. **Screenshots are not included.** `screenshots/` is empty; capture them from your own run (`docs/evidence_checklist.md`). Source-inspection screenshots must show the URL.
