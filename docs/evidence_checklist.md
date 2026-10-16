# Evidence pack: the nine screenshots

Capture each from **your own run**. Do not edit them, and keep the mock labels visible. Redact personal paths or addresses if needed.

| # | Screenshot | How to produce it |
|---|---|---|
| 1 | Source inspection with the URL visible | Your browser screenshots of the AJIO search page (you already have these), no personal data |
| 2 | A successful run: run_id, pages, products, status | `python -m src.main --run-once` (final JSON), or the dashboard Run history tab |
| 3 | Raw snapshots in timestamped partitions | File explorer or `dir data\\raw /s` showing `platform=AJIO/date=.../hour=.../<run_id>/` |
| 4 | Normalised rows with SB, SP and Organic | Dashboard -> Visibility products; pick keyword `women saree` and the latest hour; show keyword, product_name, sp, mrp, absolute_rank, relative_rank, product_type, scheduled_hour, run_id |
| 5 | Scheduler config/UI with a completed run | `config/cron.example` or the `--schedule` console after a cycle, next to Run history |
| 6 | Dashboard coverage grid | Dashboard -> Coverage grid after `--demo` (or a few `--backfill-hours`) |
| 7 | A deliberately missing slot flagged | Run `python -m src.main --run-once --hour <H-3>` and `--hour <H-1>` only, then `--check-completeness --hour <H-2>`; the grid shows `missing` in red and Alert incidents shows the open incident. (`--demo` does the same and then backfills.) |
| 8 | Test alert email (redacted) | A file from `data/outbox/` opened in a mail client or editor, or Mailpit at http://localhost:8025 with `ALERT_SINK=smtp` |
| 9 | Full test output including curveballs | `pytest -v` |

Tip: for 7, take the screenshot *before* the backfill step of `--demo`, or run the commands by hand. Every screenshot of the dashboard shows the MOCK DATA ONLY banner; keep it in frame.
