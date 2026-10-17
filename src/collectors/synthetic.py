"""Deterministic synthetic search-result pages for the mock adapter.

Everything here is invented. A keyword has a stable catalogue of fake products;
for each scheduled hour the ordering, a few prices, deals and the sponsored
slots drift in a seeded, reproducible way. That gives the pipeline data in
which ranks, prices and deals change across the day, without ever claiming to
be a real AJIO observation.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from html import escape

PAGE_SIZE = 20
ORGANIC_COUNT = 30
SP_POSITIONS = (1, 4, 15, 26)  # 0-based indexes in the combined list; SB sits at index 0
BRANDS = ("Mockwear", "Testline", "Fixtura", "Samplr", "Dummico", "Synthia", "Placeholdr", "Fakely")
COLOURS = ("white", "black", "navy", "olive", "beige", "maroon")
TAGS = ("", "", "", "Bestseller", "New", "Trending")
DEALS = ("", "", "", "Extra 10% off", "Buy 2 get 10% off", "Extra 5% off with coupon")
MARKER = "<!-- SYNTHETIC MOCK FIXTURE; generated deterministically, not fetched from AJIO. -->"


def _rng(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass(frozen=True)
class SyntheticUnit:
    kind: str  # SB | SP | ORGANIC
    name: str
    product_id: str | None
    url: str | None
    price: str | None
    mrp: str | None
    rating: str | None
    rating_count: str | None
    tag: str
    deal: str
    image: str
    campaign_id: str | None


def _money(rng: random.Random, amount: int) -> str:
    style = rng.randint(0, 2)
    if style == 0:
        return f"₹{amount:,}"
    if style == 1:
        return f"Rs. {amount}.00"
    return str(amount)


def _count(rng: random.Random, n: int) -> str:
    style = rng.randint(0, 2)
    if style == 0:
        return str(n)
    if style == 1:
        return f"({n:,})"
    return f"{n / 1000:.1f}K" if n >= 1000 else str(n)


def _product(keyword: str, index: int, slot: str, kind: str, campaign_id: str | None = None) -> SyntheticUnit:
    stable = _rng("product", keyword, index)
    brand = BRANDS[stable.randrange(len(BRANDS))]
    pid = str(900_000_000 + stable.randrange(99_999_999))
    colour = COLOURS[stable.randrange(len(COLOURS))]
    base = stable.randrange(499, 4999)
    mrp_amount = int(base * stable.uniform(1.3, 2.2))
    has_mrp = stable.random() > 0.1
    has_rating = stable.random() > 0.05
    rating = f"{stable.uniform(3.2, 4.8):.1f}"
    rating_n = stable.randrange(12, 9000)
    tag = TAGS[stable.randrange(len(TAGS))]
    hourly = _rng("hourly", keyword, index, slot)
    price = base
    if hourly.random() < 0.3:
        price = int(base * hourly.uniform(0.9, 1.1))
    deal = DEALS[hourly.randrange(len(DEALS))]
    name = f"Mock {brand} {keyword.title()} #{index + 1}"
    slug = _slug(name)
    return SyntheticUnit(
        kind=kind,
        name=name,
        product_id=pid,
        url=f"https://www.ajio.com/{slug}/p/{pid}_{colour}?src={hourly.randrange(1000, 9999)}",
        price=_money(stable, price),
        mrp=_money(stable, mrp_amount) if has_mrp else None,
        rating=rating if has_rating else None,
        rating_count=_count(stable, rating_n) if has_rating else None,
        tag=tag,
        deal=deal,
        image=f"https://example.invalid/img/{pid}.jpg",
        campaign_id=campaign_id,
    )


def build_listing(keyword: str, slot: str) -> list[SyntheticUnit]:
    """The full ordered result list (all pages) for a keyword in a given hour."""
    order = list(range(ORGANIC_COUNT))
    swaps = _rng("order", keyword, slot)
    for _ in range(3):  # a few neighbouring swaps per hour: ranks move, but only slightly
        i = swaps.randrange(len(order) - 1)
        order[i], order[i + 1] = order[i + 1], order[i]

    organic = [_product(keyword, i, slot, "ORGANIC") for i in order]
    brand = BRANDS[_rng("brand", keyword).randrange(len(BRANDS))]
    banner = SyntheticUnit(
        kind="SB", name=f"{brand} Mock Brand Banner", product_id=None, url=None, price=None, mrp=None,
        rating=None, rating_count=None, tag="", deal="", image=f"https://example.invalid/banner/{_slug(brand)}.jpg",
        campaign_id=f"MOCK-CMP-{_rng('cmp', keyword).randrange(100, 999)}",
    )
    sponsored = []
    for n, _ in enumerate(SP_POSITIONS):
        # The third sponsored unit re-uses an organic product: same product, two placements.
        catalogue_index = 7 if n == 2 else ORGANIC_COUNT + n
        sponsored.append(_product(keyword, catalogue_index, slot, "SP", campaign_id=f"MOCK-CMP-{_rng('sp', keyword, n).randrange(100, 999)}"))

    units: list[SyntheticUnit] = []
    sp_iter, org_iter = iter(sponsored), iter(organic)
    total = 1 + len(sponsored) + len(organic)
    for position in range(total):
        if position == 0:
            units.append(banner)
        elif position in SP_POSITIONS:
            units.append(next(sp_iter))
        else:
            units.append(next(org_iter))
    return units


def _card(unit: SyntheticUnit) -> str:
    """One simulated grid card.

    Product cards carry price/placement/rating data only (the SIMULATED layer). Their name, url
    and image are published in the page's JSON-LD ItemList instead (the OBSERVED layer), as on
    the real page. Brand banners are not products, so they carry their own name and image.
    """
    is_banner = unit.kind == "SB"
    attrs = {
        "data-kind": unit.kind,
        "data-name": unit.name if is_banner else None,
        "data-product-id": unit.product_id,
        "data-price": unit.price,
        "data-mrp": unit.mrp,
        "data-rating": unit.rating,
        "data-rating-count": unit.rating_count,
        "data-tag": unit.tag or None,
        "data-deal": unit.deal or None,
        "data-image": unit.image if is_banner else None,
        "data-campaign-id": unit.campaign_id,
    }
    rendered = " ".join(f'{k}="{escape(str(v), quote=True)}"' for k, v in attrs.items() if v)
    inner = f"<h2>{escape(unit.name)}</h2>" if is_banner else ""
    return f'  <article class="product-card" {rendered}>{inner}</article>'


def _item_list(chunk: list[SyntheticUnit], total_products: int, keyword: str) -> str:
    """JSON-LD ItemList in the observed shape: name, image, url, position (+ numberOfItems)."""
    products = [u for u in chunk if u.kind != "SB"]
    data = {
        "@context": "http://schema.org",
        "@type": "ItemList",
        "url": f"https://www.ajio.com/search/?text={keyword.replace(' ', '+')}",
        "numberOfItems": str(total_products),
        "itemListElement": [
            {"@type": "ListItem", "name": u.name, "image": u.image, "url": u.url, "position": n}
            for n, u in enumerate(products, start=1)
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def render_page(keyword: str, page: int, slot: str) -> str:
    listing = build_listing(keyword, slot)
    start = (page - 1) * PAGE_SIZE
    chunk = listing[start:start + PAGE_SIZE]
    if not chunk:
        return (
            f'{MARKER}\n<html><body><main><div data-testid="product-grid"></div>'
            '<p data-testid="no-results">No more products for this search.</p></main></body></html>'
        )
    cards = "\n".join(_card(u) for u in chunk)
    total_products = sum(1 for u in listing if u.kind != "SB")
    ld = _item_list(chunk, total_products, keyword)
    return f'{MARKER}\n<html><head>{ld}</head><body><section data-testid="product-grid">\n{cards}\n</section></body></html>'
