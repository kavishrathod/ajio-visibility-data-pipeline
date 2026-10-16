# Task A: Source research
- Inspected: https://www.ajio.com/search/?text=white+kurta+for+men (manual browser view only)
- robots.txt: `Disallow: /search`, `Disallow: /*/search/*`, `Disallow: /api/*` -> no automated collection
- Rendering: client-rendered grid (skeleton loaders); JSON-LD ItemList with name/image/url/position (~45 items), numberOfItems 28,073
- Product key: URL path `/p/<style>_<color>`
- Not observable: price, MRP, rating, sponsored markers
TODO: write up flow, pagination, rate assumptions, how the mock mirrors this.
