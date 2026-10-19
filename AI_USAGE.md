# AI Usage Disclosure

## My contribution and use of AI

I approached this assessment by focusing on the failure scenarios in a data pipeline, not just on getting a successful run. I worked through how the pipeline should behave when data is missing, pages are incomplete, records are duplicated, or a rerun happens for the same scheduled hour.

I worked on the project iteratively, identifying engineering problems, deciding what behaviours the pipeline needed to support, and implementing and validating solutions with assistance from Claude and ChatGPT. Depending on the task, I identified the problem or approach myself and used AI to help generate code, explore implementation options, debug issues, or improve tests and documentation. I integrated, reviewed, and tested AI-assisted changes as part of the development process.

My contributions included:

- **Pipeline reliability:** Worked through the handling of retries, rate limits, overlapping runs, missing scheduled hours, partial page failures, and recovery after failures, using AI assistance where needed to develop and refine the implementation.

- **Data integrity:** Worked with AI assistance on idempotent loading, duplicate-placement detection, record validation, and preserving raw snapshots so data could be replayed without fetching it again.

- **Quarantine layer:** Identified the need to retain rejected records instead of silently dropping them. I used AI assistance to implement storage of rejection reasons and payloads, integrate quarantine with the pipeline, develop edge-case tests, and document the behaviour and limitations.

- **Monitoring and alerting:** Reviewed and tested AI-generated code for completeness checks, alert aggregation, incident tracking, and recovery notifications so repeated failures would not simply generate repeated alerts.

- **Property-based tests:** Identified the need to test parser and data-integrity edge cases. With AI assistance, I developed and integrated Hypothesis tests for price, count and rating parsing, the product key, deduplication, and rank continuity across pages. These tests exposed two parser bugs: an out-of-range rating such as `7.5` being interpreted as `5.0`, and a title slug of `p` producing an incorrect product key. I implemented and tested fixes for both issues with AI assistance.

- **Duplicate-spike detection:** Worked out the measurement approach, including per-target-hour duplicate counts, duplicate rates, a rolling baseline, thresholds, incident wording, and test scenarios. I used AI-generated code as a starting point, integrated it into the project, and tested the resulting behaviour, including a fixture designed to produce a duplicate spike.

- **Brand comparison:** Added brand-level comparison capabilities with AI assistance, including an explicit brand field, normalization, a curated alias file, and a Gold view comparing organic ranks with sponsored placements. I decided not to infer brands from product titles to avoid introducing unsupported assumptions.

- **Test-suite speed:** Identified that the clean-clone test run was taking too long and investigated the need for optimization. With AI assistance, I worked on reducing overhead associated with SQLite commits and fixture copies while preserving the test assertions. I also added a benchmark script to measure performance on a given machine.

- **Status audit:** Checked whether the target-hour statuses required by the assessment corresponded to actual pipeline behaviour. I identified that a later-page fetch failure should result in `partial` rather than `failed` when page-one records had already been saved, and worked on correcting that behaviour.

- **Scaling note:** Worked out the estimated load, request rate, partitioning, concurrency, and rough cost for 20,000 targets. I developed the assumptions and estimates, then used AI assistance to help document and refine the explanation. The cost figures are order-of-magnitude estimates based on stated assumptions, not vendor quotes.

- **Data modelling:** Worked on normalized product records and Gold SQL views for hourly summaries, keyword coverage, product placements, and quarantine summaries, using AI assistance to help develop and refine the implementation.

- **Dashboard:** Integrated and reviewed the Streamlit dashboard with AI assistance for setup, design, and implementation. I used it to inspect pipeline runs, coverage gaps, product records, aggregates, and alert incidents.

- **GitHub Actions:** Identified the need for automated checks and a mock-mode smoke run on pushes. I used AI assistance to develop the workflow configuration, integrated it into the project, and used the checks to verify changes consistently.

- **Source investigation:** Personally inspected AJIO's search page, `robots.txt`, browser Network activity, and embedded JSON-LD. Based on this investigation, I kept automated live collection disabled and used synthetic data and fixtures instead.

- **Documentation and reproducibility:** Worked iteratively with AI assistance to draft, review, correct, and refine engineering decision records, known limitations, quarantine documentation, the evidence checklist, and clean-clone validation instructions so another person could understand and reproduce the project.

AI assistance was part of my development workflow, but it did not replace my responsibility for the project. I identified problems and made engineering decisions, integrated and reviewed AI-assisted changes, ran tests, investigated results, and refined the implementation. I am responsible for the submitted code, its behaviour, and the accuracy of the documented results and limitations.

## Validation performed

I cloned the repository into a separate folder, created a fresh virtual environment, installed the dependencies from `requirements.txt`, ran the test suite, and completed the mock demo. My latest local test run reported **143 passed in 8.83 seconds** after the test-suite optimizations. I also ran the pipeline in mock mode, checked idempotency across repeated runs, reviewed the dashboard, and examined successful targets, explicit zero-result targets, missing-hour detection, alert aggregation, backfill, and recovery.

The mock demo reported 50 targets per slot, 48 `success` results, 2 `zero_result` results, and 1,616 rows written or upserted per slot. I exported the dashboard coverage grid to CSV and checked it: 50 keywords across three scheduled-hour columns, with the two zero-result keywords marked `zero_result` in all three hours and the other 48 marked `success`.

These results are from synthetic data and local testing. They are not evidence of live AJIO collection.

## Mock Data Disclosure

The project uses a clearly identified mock adapter because live AJIO search access is restricted by the site's access guidance. Demonstrations and test results using simulated data are not presented as live AJIO extraction.
