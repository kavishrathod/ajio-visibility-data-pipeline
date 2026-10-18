# Source Research: AJIO Search Visibility (Task A)

**Date of inspection:** 16 October 2026
**Method:** manual viewing in a normal desktop Chrome session, with DevTools open in read-only mode (Network and Console tabs). No scripts, no automation, no login, no requests replayed or modified.
**Outcome:** live collection of AJIO search results is **not permitted** by robots.txt. This project uses a **clearly labelled mock adapter**. No live AJIO data is collected or presented anywhere in this repository.

---

## 1. What I inspected

### 1.1 Search URL and page flow

Searching for "white kurta for men" from the AJIO homepage led to:

```
https://www.ajio.com/search/?text=white+kurta+for+men&itm_source=search&itm_source_detail=white+kurta+for+men
```

- Path: `/search/`
- Keyword parameter: `text`
- Tracking parameters: `itm_source`, `itm_source_detail` (these do not change the results; they only record where the search came from)
- Page title: "Best Offers on White kurta for men"
- Breadcrumb: Home / white kurta for men
- Result header: "White Kurta For Men", **28,073 Items Found**

(Screenshots: `screenshots/` - source inspection, URL visible)

### 1.2 Page layout observed

| Area | What was visible |
|---|---|
| Header | Logo, MEN / WOMEN / KIDS / BEAUTY / HOME & KITCHEN nav, search box, wishlist, sign-in links |
| Promo strip | Sale banner under the header |
| Left panel "Refine By" | Shop For (Men, Boys, Women, Infants, Girls, with counts), Category (with counts), Price, Brands (collapsed) |
| Toolbar | Total items count, grid-density toggle, "Sort By" dropdown (default **Relevance**) |
| Result grid | Product cards: image, brand name shown beneath the image, then (below the fold) name and price |

### 1.3 Rendering behaviour

- On first load the page shows **grey skeleton placeholders** before any product appears (screenshot 1). Content is therefore filled in **client-side**, not delivered as finished HTML.
- The Network tab shows many `fetch` requests initiated by `fetchWrapper.mjs`, a service worker (`sw.js`) and framework bundles (`desktop-libraries`, `desktop-vendors`). Product images are loaded afterwards as separate fetches (for example `vastrado_white_men_slim_fit_kurta.jpg`).
- An ad-related script (`jioAds.js`) is loaded on the page. I did not inspect it. It suggests that sponsored placements are served through an ad component, but I have **not verified** how sponsored units are marked in the page.
- Page-source check: I opened `view-source:` for the same URL in a separate tab and searched for a product name from the results ("Vastrado"). It appears inside an embedded `<script type="application/ld+json">` block holding a schema.org `ItemList` (name, image, URL and position for each product, plus a total item count). I did not otherwise analyse whether the rendered product cards are present in the raw HTML.

### 1.4 Fields visible on a result card

Seen directly: brand and product image. Product title and price sit below the visible area in my screenshots, so I did not record the selling price, struck-through MRP, rating, rating count, discount tag, badge or any "Sponsored"/"Ad" label from the live page. Product titles are available in the JSON-LD block. I list a field as observed only if I saw it myself.

### 1.5 Pagination

In a logged-out session the results load by infinite scroll, in a grid of three products per row; I saw no numbered pages. I did not record how many items load per scroll or whether the URL changes.

### 1.6 Pincode, Size and Delivery Checks

I inspected the search results for **“white kurta for man”** and opened an individual product to examine its size-selection and delivery-check functionality.

During the inspection, I did not observe a direct pincode-check control on the main search-results page. I therefore performed the delivery checks on the individual product page.

**Tests performed:**
- Changed the size and pincode multiple times for the same product.
- Kept the size constant while changing the pincode.
- Kept the pincode constant while changing the size.
- Returned to the search-results page after changing the pincode to check whether the selected pincode was visible or whether the product listing had changed.

**Observed results:**
- The displayed delivery date remained unchanged across the variations tested.
- The selected pincode was not visible on the search-results page after returning from the product page.
- The product listing appeared unchanged after the pincode was changed.

**Conclusion:**

The inspection confirmed that size and pincode variations did not change the displayed delivery date for the tested product. However, I could not verify whether the selected pincode was applied in the search-results context or whether pincode influences product visibility or ranking. These behaviours remain unverified based on the checks performed.

### 1.7 Sponsored product identification

On an inspected product unit in the search results, I observed an "Ad" label in the top-left corner of the product image. I use this visible label as evidence for identifying that product unit as a sponsored product (SP). I did not independently verify a sponsored brand banner (SB) during this inspection. Any SB placements in the mock adapter are simulated and are labelled accordingly.

---

## 2. What I could not and did not access, and why

AJIO's robots.txt (`https://www.ajio.com/robots.txt`) states, among other rules, for `User-agent: *`:

```
Disallow: /search
Disallow: /*/search/*
Disallow: /api/*
Disallow: /api/
Disallow: /*?q=
Disallow: /*?query=      (except under /fc/ and /fb/)
```

Consequences:

1. The search page I inspected (`/search/?text=...`) is on a **disallowed path**, so automated collection of it is not permitted.
2. The JSON/XHR endpoints that the page calls for product data fall under `/api/` and are not documented for public use. I did **not** call, replay or reverse-engineer them.
3. I did not use proxies, rotating identities, headless or stealth browsers, CAPTCHA solving, cookies or logins, in line with the brief's ground rules.
4. Authenticated areas (account, cart, wishlist, checkout) are also disallowed and were not touched.

The one brief-permitted exception, `/fc/` and `/fb/` pages with `?query=`, are category and brand-store style pages. These are not keyword search results, so they do not answer the "visibility for a keyword" question. I did not use them.

**Not verified:** whether results vary by pincode, whether sort order changes the sponsored placement, and the exact markup used for sponsored units.

---

## 3. Decision

Per the brief ("if live access is blocked or not permitted, stop, document what you saw, and build a mock adapter"):

- The pipeline uses a **mock adapter**. Live collection is disabled in code (`AjioAdapter` raises `PermissionError`) and in configuration (`adapter: mock`; the CLI refuses `adapter: live`).
- The adapter sits behind the same one-method fetch interface a live adapter would use, so a compliant source (for example an official partner feed, if one were ever provided) could replace it without touching the parser, storage or monitoring code.
- The dashboard shows a "MOCK DATA ONLY" banner, every database row carries `is_mock`, and every mock page contains a `SYNTHETIC MOCK FIXTURE` marker that the adapter checks.

---

## 4. How the mock reflects what I observed

| Observed on AJIO | In the mock |
|---|---|
| Keyword search via a `/search/?text=` page, default sort Relevance | Targets are keywords; sort order is fixed to relevance; the mock is addressed by keyword and page number, not by URL |
| A schema.org JSON-LD `ItemList` embedded in the page source, with `name`, `image`, `url`, `position` per item and `numberOfItems` (28,073) | **Modelled as observed.** Every mock page embeds a `<script type="application/ld+json">` `ItemList` with exactly those fields. The parser takes each product's name, URL and image from it, and records `numberOfItems` |
| Grid of cards with brand, name, image, price | **Simulated.** Each card is an `<article class="product-card">` inside `[data-testid="product-grid"]`, with `data-*` attributes for price, MRP, rating, count, tag, deal, placement. The JSON-LD does not contain these fields, so this layer is invented; I did not inspect the rendered DOM |
| An ad component (`jioAds.js`) loaded on the page | Cards carry `data-kind` = `SB`, `SP` or organic, and `data-campaign-id` on paid units. **This marker is invented for the mock; I did not verify how AJIO marks sponsored units** |
| Result counts such as "28,073 Items Found" | Not modelled. A genuine zero-result page is a grid with no cards and an explicit no-results message |
| Infinite scroll in a logged-out session | **Not modelled.** The mock serves numbered pages (page 1, page 2) per keyword, which is a simplification; how a real source would be paged is unknown |
| Client-side rendering: skeleton loaders, then fetch calls | **Not modelled.** The mock returns static HTML with the grid already present, which is a simplification. The JSON-LD block is the only layer that exists in the page source as observed |

**Design rule that follows from this:** the JSON-LD cannot tell a sponsored unit from an organic one, and has no price. So it is never trusted to decide a page is healthy: a page with JSON-LD but no product grid is `parse_failed` (fixture `layout_changed_jsonld_present.html`, test `test_json_ld_does_not_rescue_a_page_whose_grid_is_missing`). A mismatch between the JSON-LD and the grid (different product at the same position, or different item counts) is logged as a parser warning.

The mock cannot support any claim about real AJIO ranking, prices, ratings or campaigns: they are simulated.

---

## 5. Assumptions the brief asks me to state (for the mock)

| Question | Assumption | Why |
|---|---|---|
| Pages per keyword | 2 pages, up to 20 units each in the generator (`max_pages` per target) | 50 keywords x 2 pages = 100 requests. The live page uses infinite scroll; two pages is an assumption |
| Request rate | 1 request every 2 s (0.5 rps) with jittered backoff on retries; `Retry-After` honoured within a 10 s budget | 100 requests take about 200 s plus response time, far inside the hour. The mock is exempt by default since it does no network I/O |
| Sort order | Relevance (the site default) | What a shopper sees first |
| Pincode | Not varied; results assumed pincode-independent in the mock | Unverified on the live site |
| Placement types | `Organic`, `SP` (sponsored product), `SB` (sponsored brand banner) | As in the brief; real markup unverified |
| Product identity | `product_id` from the canonical `/p/<id>` URL path with tracking parameters removed. Never the title | Titles repeat and change |
| Missing product | Never treated as out of stock unless the page says so | Per the brief |
| `platform` / `platform_code` | `AJIO` / `search` | Only keyword search results are collected, so every unit comes from the `search` surface |

---

## 6. Honesty statement

- All rows in the database are synthetic mock data, labelled as such.
- Screenshots of the live site are from manual browsing only and appear as source-inspection evidence, not as extracted data.
