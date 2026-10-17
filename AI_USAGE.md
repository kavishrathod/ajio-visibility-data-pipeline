# AI Usage Disclosure

## My contribution and use of AI

I approached this assessment by focusing on the failure scenarios in a data pipeline, not just on getting a successful run. I worked through how the pipeline should behave when data is missing, pages are incomplete, records are duplicated, or a rerun happens for the same scheduled hour.

I used Claude and other AI coding assistance to explore implementation options, work through complex code changes, debug issues, and improve tests and documentation. I made changes to the project as I worked through these problems and validated the resulting behaviour locally.

My contributions included:

- **Pipeline reliability:** Worked through the handling of retries, rate limits, overlapping runs, missing scheduled hours, partial page failures, and recovery after failures.
- **Data integrity:** Worked on idempotent loading, duplicate-placement detection, record validation, and preserving raw snapshots so data could be replayed without fetching it again.
- **Quarantine layer:** Identified the need to retain rejected records instead of silently dropping them. Worked on storing rejection reasons and payloads, integrating quarantine with the pipeline, adding tests for edge cases, and documenting the behaviour and limitations.
- **Monitoring and alerting:** Worked on completeness checks, alert aggregation, incident tracking, and recovery notifications so repeated failures would not simply generate repeated alerts.
- **Data modelling:** Worked on normalized product records and Gold SQL views for hourly summaries, keyword coverage, product placements, and quarantine summaries.
- **Dashboard:** Integrated and reviewed the Streamlit dashboard to make pipeline runs, coverage gaps, product records, aggregates, and alert incidents easier to inspect.
- **GitHub Actions:** Set up CI checks to run the test suite and a mock-mode smoke run on pushes, making it easier to verify changes consistently.
- **Source investigation:** Inspected AJIO's search page, `robots.txt`, browser Network activity, and embedded JSON-LD. Based on that investigation, I kept automated live collection disabled and used synthetic data and fixtures instead.
- **Documentation and reproducibility:** Worked on the engineering decision records, known limitations, quarantine documentation, evidence checklist, and clean-clone validation so another person could understand and reproduce the project.

AI assistance was particularly useful for exploring implementation approaches, working through debugging issues, and developing edge-case tests. I reviewed the changes, ran the project, investigated the results, and made further changes where needed. The final implementation also includes documented limitations rather than presenting the local mock pipeline as a production-ready live collector.

## Validation performed

I cloned the repository into a separate folder, created a fresh virtual environment, and ran the test suite. The suite grew from 86 passing tests before the quarantine layer to 94 passing tests afterward; the recorded clean-clone run of the final suite took 470.30 seconds.

I also ran the pipeline in mock mode, checked idempotency across repeated runs, reviewed the dashboard, and examined the output for successful targets, explicit zero-result targets, missing-hour detection, alert aggregation, backfill, and recovery.

The observed run reported 50 targets per slot, 48 `success` results, 2 `zero_result` results, and 1,616 rows written or upserted per slot.

These results are from synthetic data and local testing. They are not evidence of live AJIO collection.