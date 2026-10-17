# AI Usage Disclosure

## Tools used

AI coding assistants, including Claude, were used during development to
help interpret the assessment brief, review the starter repository,
suggest implementation approaches, draft and revise code,
generate/refine tests, debug issues, and draft documentation.

AI assistance covered areas including mock data/fixtures, parsing and
normalization, retry/backoff and rate limiting, overlap locking, raw
replay, completeness checks, alert aggregation/recovery, dashboard
presentation, tests, and written explanations. The output was reviewed
and adapted as part of the project workflow.

Later changes drafted with AI assistance, in order: moving slots from UTC hours
to IST hours; adding the JSON-LD identity layer to the mock pages and parser;
adding the Gold SQL views and dashboard tab; a status audit test and a fix so a
later-page fetch failure is `partial` rather than `failed`; a GitHub Actions
workflow; `scripts/check_idempotency.py` and `scripts/show_quarantine.py`; the
quarantine layer; and the matching documentation updates.

## Human review and validation

The project author performed the following checks:

-   Cloned the GitHub repository into a separate clean folder and used a
    fresh virtual environment.
-   Ran `python -m pytest -q`: **86 passed in 375.12 seconds** (the suite size
    at that time, before the quarantine layer) and **94 passed in 470.30 seconds** (after the quarantine layer)
-   Inspected AJIO's search page and `robots.txt` in a normal browser session,
    checked the Network tab and the embedded JSON-LD, and used that to decide on
    a mock-only source.
-   Ran `python -m src.main --run-once`, re-ran the same hour, and checked with
    `scripts/check_idempotency.py` that rows per slot equal distinct
    target-and-rank counts, so the rerun did not duplicate rows.
-   Reviewed the dashboard's coverage grid with a deliberately missing slot, and
    the incident table showing an open incident and a resolved one with a single
    recovery.
-   Resolved a rejected `git push` by rebasing onto a README edit made on GitHub.
-   Ran `python -m src.main --demo` successfully in mock mode.
-   Observed 50 targets per slot, 48 `success`, 2 explicit
    `zero_result`, 1,616 rows written/upserted per slot, missing-slot
    detection, repeated-alert aggregation, late backfill, 100%
    completeness, and incident resolution.
-   Opened the Streamlit dashboard locally and reviewed the overview,
    coverage grid, normalized product rows, Gold aggregates, and alert
    incident/recovery views.


## Data integrity and source restrictions

The project uses synthetic data and labelled fixtures only. Automated
live AJIO collection is disabled because the source research found the
relevant search/API paths disallowed. No synthetic product, price,
rating, campaign, or placement is represented as a real AJIO
observation. The implementation does not attempt to bypass restrictions
with stealth, proxies, CAPTCHA bypass, or unauthorized endpoints.

## Responsibility

I am responsible for the submitted work and should be able to explain:

-   idempotency and duplicate-placement rules;
-   the distinction between `zero_result`, `parse_failed`, `blocked`,
    and `failed`;
-   scheduled-hour handling and IST/UTC conversion;
-   overlap locking and retries;
-   raw snapshot persistence and replay;
-   what is quarantined and why, and why quarantine never changes a status;
-   the Gold views and why they are views rather than tables;
-   why a later-page fetch failure is `partial`;
-   completeness calculations and the alert lifecycle;
-   limitations of the mock parser and local SQLite architecture.

AI was used as a development aid. Test output and demo results are
reported as observed, and no claim of live AJIO collection is made.
