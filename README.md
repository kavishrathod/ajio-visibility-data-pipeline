# AJIO Visibility Data Pipeline (Infytrix assessment)

> **Data source: MOCK ONLY.** AJIO's robots.txt disallows `/search` and `/api/*`, so no automated live
> collection is performed. All fixtures are simulated and labelled `"_mock": true`.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest
```

## TODO sections (required by the brief)
Configure targets · run one collection · backfill a past hour · how hourly scheduling works ·
where data lives · trigger a missing-slot alert · configure email safely · recover from failure ·
what is mocked vs live.

## Layout
`config/` targets + settings · `src/ajio_pipeline/` code · `sql/` DDL · `tests/fixtures/` mock pages ·
`docs/` architecture, data dictionary, source research · `screenshots/` evidence pack.
