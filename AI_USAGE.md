# AI Usage Disclosure

## My contribution and use of AI

I approached this assessment by focusing on the failure scenarios in a data pipeline, not just on getting a successful run. I worked through how the pipeline should behave when data is missing, pages are incomplete, records are duplicated, or a rerun happens for the same scheduled hour.

I used Claude and other AI coding assistance to explore implementation options, work through complex code changes, debug issues, and improve tests and documentation. I made changes to the project as I worked through these problems and validated the resulting behaviour locally.

My contributions included:

- **Pipeline reliability:** Worked through the handling of retries, rate limits, overlapping runs, missing scheduled hours, partial page failures, and recovery after failures.
- **Data integrity:** Worked on idempotent loading, duplicate-placement detection, record validation, and preserving raw snapshots so data could be replayed without fetching it again.
- **Quarantine layer:** Identified the need to retain rejected records instead of silently dropping them. Worked on storing rejection reasons and payloads, integrating quarantine with the pipeline, adding tests for edge cases, and documenting the behaviour and limitations.
- **Monitoring and alerting:** Worked on completeness checks, alert aggregation, incident tracking, and recovery notifications so repeated failures would not simply generate repeated alerts.
- **Property-based tests:** Wrote Hypothesis tests for price, count and rating parsing, the product key, deduplication, and rank continuity across pages. They found two parser bugs, an out-of-range rating such as `7.5` being read as `5.0` and a title slug of `p` producing the wrong product key, and I fixed both.
- **Duplicate-spike detection:** Designed the measurement (a per-target-hour duplicate count, a rate, and a rolling baseline), the thresholds, the incident wording and the tests, including a fixture that produces a spike.
- **Brand comparison:** Added an explicit brand field with normalization and a curated alias file, and a Gold view comparing each brand's organic rank with its sponsored placements. I decided not to infer brands from product titles.
- **Test-suite speed:** Profiled where the slow clean-clone run spends its time (SQLite commits and fixture copies), then reduced that work without changing any assertion, and added a benchmark script to measure it on a given machine.
- **Status audit:** Checked that every target-hour status in the brief is produced by real behaviour, and changed a later-page fetch failure from `failed` to `partial` because the page-1 rows had already been saved.
- **Scaling note:** Worked out the load, request rate, partitioning, concurrency and rough cost for 20,000 targets. The cost figures are order-of-magnitude estimates based on stated assumptions, not quotes.
- **Data modelling:** Worked on normalized product records and Gold SQL views for hourly summaries, keyword coverage, product placements, and quarantine summaries.
- **Dashboard:** Integrated and reviewed the Streamlit dashboard to make pipeline runs, coverage gaps, product records, aggregates, and alert incidents easier to inspect.
- **GitHub Actions:** Set up CI checks to run the test suite and a mock-mode smoke run on pushes, making it easier to verify changes consistently.
- **Source investigation:** Inspected AJIO's search page, `robots.txt`, browser Network activity, and embedded JSON-LD. Based on that investigation, I kept automated live collection disabled and used synthetic data and fixtures instead.
- **Documentation and reproducibility:** Worked on the engineering decision records, known limitations, quarantine documentation, evidence checklist, and clean-clone validation so another person could understand and reproduce the project.

AI assistance was particularly useful for exploring implementation approaches, working through debugging issues, and developing edge-case tests. I reviewed the changes, ran the project, investigated the results, and made further changes where needed. The final implementation also includes documented limitations rather than presenting the local mock pipeline as a production-ready live collector.

## Validation performed

I cloned the repository into a separate folder, created a fresh virtual environment, installed the dependencies from `requirements.txt`, ran the test suite, and completed the mock demo. My latest local test run reported **143 passed in 8.83 seconds** after the test-suite optimisations. I also ran the pipeline in mock mode, checked idempotency across repeated runs, reviewed the dashboard, and examined successful targets, explicit zero-result targets, missing-hour detection, alert aggregation, backfill, and recovery.

The mock demo reported 50 targets per slot, 48 `success` results, 2 `zero_result` results, and 1,616 rows written or upserted per slot. I exported the dashboard coverage grid to CSV and checked it: 50 keywords across three scheduled-hour columns, with the two zero-result keywords marked `zero_result` in all three hours and the other 48 marked `success`.

These results are from synthetic data and local testing. They are not evidence of live AJIO collection.
