# Source Research: AJIO Search Visibility (Task A)

**Date of inspection:** 16–19 October 2026
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
- Result header: "White Kurta For Men". I observed **28,073 Items Found** in an earlier session and **27,854 Items Found** in a later session. The displayed count changed between sessions.

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
- I opened `view-source:` for the search URL in a separate tab. I did not record enough detail to make a reliable claim about whether the full product grid was present in the initial raw HTML.

### 1.4 Fields visible on result cards and product pages

On the search-results page, I observed product cards and later inspected two linked JOMPERS product-detail pages. I used the browser's rendered page and Chrome DevTools in read-only mode; I did not run scripts, automate collection, or replay requests.

**Search-results page observations:**

- I observed an `Ad` label on one product image in the search results. I did not establish the underlying markup or the rule that determines sponsored placement.
- In a later session, I changed sorting/filtering options including Discount, What's New, and price filters. The displayed products changed. Under What's New, I observed an Ad-labelled unit in each visible row during that session. This is a session-specific observation, not proof of a universal placement rule.
- I did not establish whether the same products retain sponsored status or whether the sponsored placements move consistently across all sort/filter settings.

**Search-results DOM check:** I inspected the rendered search page here: [AJIO search — white kurta for men](https://www.ajio.com/search/?text=white+kurta+for+men&itm_source=search&itm_source_detail=white%2Bkurta%2Bfor%2Bmen). I observed an Ad label on one result image; I did not verify the underlying sponsored-unit markup.

**Product-detail page DOM check:**

I inspected these two JOMPERS product pages:

1. [JOMPERS — Printed Regular Fit Kurta & Pyjamas Set](https://www.ajio.com/jompers-printed-regular-fit-kurta--pyjamas-set/p/704186149_white?itm_source=search&itm_source_detail=white%2Bkurta%2Bfor%2Bmen)
2. [JOMPERS — Embroidered Regular Fit Kurta & Pyjamas Set](https://www.ajio.com/jompers-embroidered-regular-fit-kurta--pyjamas-set/p/704186223_purple?itm_source=search&itm_source_detail=white%2Bkurta%2Bfor%2Bmen)

I observed the same classes on both pages for the product title (`prod-name`), brand (`brand-name`), and MRP label (`prod-mrp`). The first page showed the title “Printed Regular Fit Kurta & Pyjamas Set”, brand JOMPERS, MRP ₹3,499, and a conditional promotional price of ₹2,974 with code `ALLSTARS15`. The second page showed “Embroidered Regular Fit Kurta & Pyjamas Set”, brand JOMPERS, MRP ₹3,499, and the same conditional promotional price of ₹2,974 with code `ALLSTARS15`.

For the first product, the page stated “No rating or review to display.” I did not confirm the rating state for the second product. I did not observe an `Ad` label on either product-detail page; that does not establish whether either item was sponsored on the search-results page.

The DOM snippets I observed included:

```html
<h1 role="heading" aria-level="2" class="prod-name" aria-label="Printed Regular Fit Kurta & Pyjamas Set">Printed Regular Fit Kurta & Pyjamas Set</h1>
<h2 role="heading" aria-level="1" class="brand-name" aria-label="JOMPERS">JOMPERS</h2>
<span class="prod-mrp" aria-label="MRP">MRP</span>
```

I confirmed these class names on two JOMPERS product pages only. I do not assume that every AJIO product uses identical markup. The MRP label snippet itself contains the label, not the price amount; I read the ₹3,499 amount from the rendered product page.

### 1.5 Pagination and loading

In a later search session, the page showed **27,854 Items Found**. I did not see numbered pagination. I observed approximately 14 rows with three product cards per row (about 42 visible cards) before more results loaded as I reached the end. This supports an infinite-scroll or load-more behaviour in that session; it does not mean all displayed results were loaded at once. I did not record whether the URL changed during scrolling.

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

**Pincode and delivery behaviour:** While logged out, I did not find an option to change the pincode directly on the search-results page. I could check the pincode only after opening an individual product page. In the product-level checks I performed, changing the pincode did not visibly change the displayed delivery date. I did not verify whether pincode affects search ranking, product availability, or results across other products.

**Still not established:** the exact underlying markup and rules for sponsored placements; whether the sponsored placements change consistently across sort/filter settings; and whether the observed scroll batch size is consistent across sessions.

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
| Grid of cards with brand, name, image, price | Each card is an `<article class="product-card">` inside `[data-testid="product-grid"]`, with `data-*` attributes for name, price, MRP, rating, count, tag, deal, image, URL |
| An ad component (`jioAds.js`) loaded on the page | Cards carry `data-kind` = `SB`, `SP` or organic, and `data-campaign-id` on paid units. **This marker is invented for the mock; I did not verify how AJIO marks sponsored units** |
| Result counts such as "28,073 Items Found" and "27,854 Items Found" | Not modelled. A genuine zero-result page is a grid with no cards and an explicit no-results message |
| Client-side rendering: skeleton loaders, then fetch calls | **Not modelled.** The mock returns static HTML, which is a simplification. A real client-rendered page could not be parsed this way |

The mock cannot support any claim about real AJIO ranking, prices, ratings or campaigns: they are simulated.

---

## 5. Assumptions the brief asks me to state (for the mock)

| Question | Assumption | Why |
|---|---|---|
| Pages per keyword | 2 pages, up to 20 units each in the generator (`max_pages` per target) | 50 keywords x 2 pages = 100 requests |
| Request rate | 1 request every 2 s (0.5 rps) with jittered backoff on retries; `Retry-After` honoured within a 10 s budget | 100 requests take about 200 s plus response time, far inside the hour. The mock is exempt by default since it does no network I/O |
| Sort order | Relevance (the site default) | What a shopper sees first |
| Pincode | Not varied in the mock; no logged-out search-page control was available during inspection | On individual product pages, changing the pincode did not visibly change the delivery date in the checks performed; effects on search ranking, availability, and other products remain unverified |
| Placement types | `Organic`, `SP` (sponsored product), `SB` (sponsored brand banner) | As in the brief; real markup unverified |
| Product identity | `product_id` from the canonical `/p/<id>` URL path with tracking parameters removed. Never the title | Titles repeat and change |
| Missing product | Never treated as out of stock unless the page says so | Per the brief |
| `platform` / `platform_code` | `AJIO` / `search` | Only keyword search results are collected, so every unit comes from the `search` surface |

---

## 6. Honesty statement

- All rows in the database are synthetic mock data, labelled as such.
- Screenshots of the live site are from manual browsing only and appear as source-inspection evidence, not as extracted data.
- I distinguish direct browser observations from assumptions and mock-only behaviour. I do not claim that the mock parser reproduces AJIO’s live DOM or that the project collects live AJIO search results.
