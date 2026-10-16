# Mock fixture format

All mock data is simulated and labelled `"_mock": true`. Structure mirrors what was observed on AJIO
(see source_research.md): `name`, `url`, `image`, `position` from the JSON-LD `ItemList`.
Price, rating, ad-placement fields are SIMULATED assumptions: they were not observable without
automated access to disallowed paths.

```json
{
  "_mock": true,
  "scenario": "I-3",
  "keyword": "men white sneakers",
  "page": 1,
  "http": {"status": 200, "headers": {"Retry-After": "2"}, "raise": null},
  "body": "<JSON text of the simulated page>"
}
```

Body shapes the parser must distinguish:

| Case | Body marker | Expected ParseResult |
|---|---|---|
| Normal page | `grid.units` non-empty | `ok` |
| Genuine zero results (I-2) | `grid.units == []` and `no_results_message` present | `zero_result` |
| Silent layout change (I-1) | `grid` key missing/renamed, HTTP 200 | `parse_failed` |
| Throttled (I-7) | `http.status = 429`, `Retry-After` header | fetcher waits (bounded) |
| Blocked (I-7) | `http.status = 403` or challenge text | `blocked`, no retry |
| Timeout | `http.raise = "timeout"` | fetcher retries with backoff |

Unit `kind`: `SB` (brand banner), `SP` (sponsored product), `ORGANIC`.
