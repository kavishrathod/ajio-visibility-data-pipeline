# Mock fixture format

Fixtures are ordinary HTML files with an explicit synthetic-data comment. They are not downloaded from AJIO and must not be described as live observations. Each page uses a purposely small, testable contract:

- `[data-testid="product-grid"]` is the expected result grid.
- `.product-card` is one observed placement.
- `data-kind` is `ORGANIC`, `SP`, or `SB`.
- `data-name`, `data-product-id`, `data-url`, `data-price`, `data-mrp`, `data-rating`, `data-rating-count`, `data-tag`, `data-deal`, `data-image`, `data-campaign-id`, and `data-brand` are optional field attributes. `data-brand` (or a `[data-testid='brand']` element) is the only source of the brand; the parser never reads it from the title.
- `[data-testid="no-results"]` with non-empty text is the only explicit zero-results marker.
- An optional `<script type="application/ld+json">` block holds a schema.org `ItemList` (`name`, `image`, `url`, `position`, `numberOfItems`), which mirrors the structure observed on the real page. When a non-banner card has no `data-name` / `data-url` / `data-image`, those come from the k-th `ItemList` entry (k-th non-banner card, in `position` order), after a product-id sanity check. Price, rating, tag, deal, placement and campaign exist only on the card (simulated layer).

| Fixture | Expected outcome | Curveball |
|---|---|---|
| `normal_results.html` | `ok` | ordinary product cards, multiple currencies/formats |
| `zero_results.html` | `zero_result` | valid empty result with explicit marker |
| `layout_changed.html` | `parse_failed` | expected grid is absent |
| `mixed_placements.html` | `ok` | `SB`, `SP`, and Organic placement types in the same order |
| `pagination_drift_page1.html`, `pagination_drift_page2.html` | `ok` with a repeated placement | I-4: same product on both pages |
| `bot_challenge.html` | `blocked` | I-7: challenge page with HTTP 200 |
| `small_page.html` | `ok` (2 units) | sudden row-count drop |
| `jsonld_identity.html` | `ok`, names/URLs/images from JSON-LD, `total_items` 1200 | observed identity layer joined to simulated grid; same product as SP and Organic |
| `layout_changed_jsonld_present.html` | `parse_failed` | I-1 variant: JSON-LD intact but grid renamed; JSON-LD must not mask the failure |
| `jsonld_mismatch.html` | `ok` with warnings | JSON-LD and grid disagree (different product at a position, different counts) |
| `quarantine_cards.html` | `ok` (2 units) with 3 quarantined records | a card with no name, a card with no id or URL, and a repeated placement |
| `duplicate_spike.html` | `ok` (6 units) with 3 duplicates | a page that repeats 3 of its 6 placements; drives the duplicate-spike tests |
| `brand_placements.html` | `ok` (10 units) | brand labels: SB, SP and Organic units of the same brand, a padded variant (`ALPHA `), a unit with no brand label but the brand in its title, a `N/A` placeholder, a paid-only brand, and an alias candidate (`Alpha Co.`) |
| `messy_values.html` | `ok` with nulls and duplicate later removed | ambiguous price range, malformed rating, suffix counts, duplicate placement |

The parser contract does not claim that this attribute structure is AJIO's live HTML. A real source adapter must be researched and permission-checked separately.

Besides fixtures, `src/collectors/synthetic.py` generates deterministic pages (seeded by keyword, page and scheduled hour) in the same structure (product identity published in JSON-LD, money and placement on the cards): 1 SB banner, 4 SP and 30 Organic units over two pages, with the SB first and SP at positions 2 and 5. Ordering, a few prices and deals drift hour to hour. Every generated page carries the `SYNTHETIC MOCK FIXTURE` comment.
