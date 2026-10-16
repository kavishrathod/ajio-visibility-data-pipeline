# AI usage disclosure

AI coding assistants (Claude) were used throughout this project: reviewing the brief and the AI-generated starter repository, auditing it against the brief, drafting and revising code (retry/jitter, rate limiter, lock handling, alert engine, mock generator, reload path, dashboard), writing tests, and drafting documentation.

How the output was checked:
- The full test suite runs from a clean install (`pytest -q`).
- Each key behaviour was removed one at a time (mutation check) to confirm a test fails; all 16 removals were caught.
- A demo run (`python -m src.main --demo`) and the dashboard were run against real tables.

Not delegated to AI: reading AJIO's robots.txt, deciding not to automate live collection, inspecting the site manually in a browser, and capturing screenshots. [Edit this file so it accurately describes your own work before submitting.]

I am responsible for every line submitted and can explain the lock handling, retry/jitter policy, parser outcomes, idempotency key, completeness logic, alert lifecycle and reload path. No synthetic fixture or generated page is presented as a live AJIO result.
