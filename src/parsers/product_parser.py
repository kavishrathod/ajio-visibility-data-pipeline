"""Parse synthetic/static product-grid HTML and normalize messy values.

Two layers, mirroring what was observed on the real search page (docs/source_research.md):

* a schema.org JSON-LD ``ItemList`` in a ``<script type="application/ld+json">`` block, which
  AJIO's page embeds and which carries identity fields only: name, image, url, position, and
  ``numberOfItems``. This is the observed structure.
* a rendered product grid carrying price, MRP, rating, tag, deal, placement kind and campaign.
  The real grid is client-rendered and was not inspected, so this layer is SIMULATED.

Identity fields come from the JSON-LD when a card does not carry them. The JSON-LD never
rescues a page whose grid is missing: placement and price live only in the grid, so a page with
JSON-LD but no grid is ``parse_failed``, not ``ok`` and not ``zero_result``.

The parser deliberately distinguishes a valid no-results marker from an absent or renamed
grid. It is not an assertion about AJIO's actual current page DOM.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


_PRODUCT_RE = re.compile(r"/p/([A-Za-z0-9-]+)(?:_([A-Za-z0-9-]+))?")


@dataclass
class ProductUnit:
    product_type: str
    product_name: Optional[str] = None
    product_url: Optional[str] = None
    product_id: Optional[str] = None
    sp: Optional[str] = None
    mrp: Optional[str] = None
    rating: Optional[float] = None
    num_of_rating: Optional[int] = None
    tag: str = ""
    deal: str = ""
    product_image_u: Optional[str] = None
    campaign_id: Optional[str] = None


@dataclass
class RejectedCard:
    """A product card the parser could not turn into a record. Feeds the quarantine layer."""
    card_index: int            # 1-based position of the card within the page grid
    reason_code: str           # card_missing_name | card_missing_identity
    detail: str
    payload: dict = field(default_factory=dict)  # attributes and a text snippet of the card, for diagnosis


@dataclass
class ParseResult:
    status: str  # ok | zero_result | parse_failed | blocked
    units: list[ProductUnit] = field(default_factory=list)
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    total_items: Optional[int] = None  # JSON-LD ItemList.numberOfItems, when present
    rejected: list[RejectedCard] = field(default_factory=list)  # cards dropped for quarantine


def parse_price(value: str | None) -> str | None:
    """Parse a single price into a decimal string; ranges and missing values stay NULL."""
    if not value:
        return None
    text = value.strip()
    if not text or text.lower() in {"n/a", "na", "not listed", "price unavailable", "-", "—"}:
        return None
    # A price range is ambiguous for price visibility analytics, so do not guess.
    if re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:-|–|—|\bto\b)\s*(?:₹|rs\.?\s*)?\d", text, re.I):
        return None
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1).replace(",", ""))
        if amount < 0:
            return None
        return f"{amount:.2f}"
    except InvalidOperation:
        return None


def parse_count(value: str | None) -> int | None:
    """Parse counts such as ``1.2K`` and ``(1,234)``; never convert missing to 0."""
    if not value:
        return None
    text = value.strip().strip("() ").replace(",", "")
    if text.lower() in {"", "—", "-", "na", "n/a", "not rated"}:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmM]?)", text)
    if not match:
        return None
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2).lower()]
    return int(round(float(match.group(1)) * multiplier))


def parse_rating(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"(?<!\d)([0-5](?:\.\d+)?)(?!\d)", value)
    if not match:
        return None
    try:
        score = float(match.group(1))
    except ValueError:
        return None
    return score if 0 <= score <= 5 else None


def product_key(url: str | None) -> str | None:
    """Stable product key extracted from a URL path, ignoring tracking parameters."""
    if not url:
        return None
    match = _PRODUCT_RE.search(urlsplit(url).path)
    if not match:
        return None
    return f"{match.group(1)}_{match.group(2)}" if match.group(2) else match.group(1)


def _field(card, attr: str, selector: str | None = None) -> str | None:
    value = card.get(attr)
    if value and str(value).strip():
        return str(value).strip()
    if selector:
        node = card.select_one(selector)
        if node:
            candidate = node.get("content") or node.get_text(" ", strip=True)
            if candidate:
                return str(candidate).strip()
    return None


def _card_payload(card) -> dict:
    """Diagnostic copy of a rejected card: its attributes (class list flattened) and a short text snippet."""
    attrs = {k: (" ".join(v) if isinstance(v, list) else v) for k, v in card.attrs.items()}
    return {"attributes": attrs, "text": card.get_text(" ", strip=True)[:200]}


def parse_item_list(soup) -> tuple[list[dict], Optional[int], list[str]]:
    """Read the JSON-LD ``ItemList``: ([{position,name,url,image}, ...] sorted by position, numberOfItems, warnings)."""
    items: list[dict] = []
    total: Optional[int] = None
    warnings: list[str] = []
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            warnings.append("JSON-LD block is not valid JSON; ignored")
            continue
        for node in (data if isinstance(data, list) else [data]):
            if not isinstance(node, dict) or node.get("@type") != "ItemList":
                continue
            try:
                total = int(str(node.get("numberOfItems", "")).replace(",", ""))
            except ValueError:
                total = total
            for entry in node.get("itemListElement") or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    position = int(entry.get("position"))
                except (TypeError, ValueError):
                    position = len(items) + 1
                items.append({
                    "position": position,
                    "name": (entry.get("name") or "").strip() or None,
                    "url": entry.get("url") or None,
                    "image": entry.get("image") or None,
                })
    items.sort(key=lambda i: i["position"])
    return items, total, warnings


def parse_products(body: str, http_status: int = 200) -> ParseResult:
    """Parse one HTML page into a typed outcome; HTTP status is checked first."""
    if http_status in {401, 403, 429}:
        return ParseResult("blocked", reason=f"HTTP {http_status}; no parser retry/bypass attempted")
    if http_status >= 400:
        return ParseResult("parse_failed", reason=f"Unexpected HTTP status {http_status}")

    soup = BeautifulSoup(body or "", "html.parser")
    ld_items, total_items, ld_warnings = parse_item_list(soup)
    for script in soup.find_all("script"):
        script.decompose()  # script text (JSON-LD) must not trigger challenge-marker detection
    text_lower = soup.get_text(" ", strip=True).lower()
    challenge_markers = ("captcha", "verify you are human", "access denied", "automated requests", "security challenge")
    if any(marker in text_lower for marker in challenge_markers):
        return ParseResult("blocked", reason="Challenge/access-denied marker detected")

    grid = soup.select_one('[data-testid="product-grid"]')
    no_results = soup.select_one('[data-testid="no-results"]')
    if grid is None:
        return ParseResult("parse_failed", reason="Expected product grid container is missing")

    cards = grid.select(".product-card")
    if not cards:
        if no_results is not None and no_results.get_text(" ", strip=True):
            return ParseResult("zero_result", reason="Explicit no-results marker found")
        return ParseResult("parse_failed", reason="Grid exists but has no product cards and no no-results marker")

    units: list[ProductUnit] = []
    rejected: list[RejectedCard] = []
    warnings: list[str] = list(ld_warnings)
    product_cards = sum(1 for c in cards if (_field(c, "data-kind") or "").strip().upper() != "SB")
    if ld_items and len(ld_items) != product_cards:
        warnings.append(f"JSON-LD lists {len(ld_items)} items but the grid has {product_cards} non-banner cards")
    ld_cursor = 0  # the k-th non-banner card is matched to the k-th JSON-LD entry (by position order)
    for idx, card in enumerate(cards, start=1):
        raw_kind = (_field(card, "data-kind") or "ORGANIC").strip().upper()
        product_type = raw_kind if raw_kind in {"SP", "SB"} else "Organic"
        ld = None
        if product_type != "SB":
            if ld_cursor < len(ld_items):
                ld = ld_items[ld_cursor]
            ld_cursor += 1
        card_pid = _field(card, "data-product-id")
        if ld and card_pid and ld["url"]:
            ld_key = product_key(ld["url"])
            if ld_key and not ld_key.startswith(card_pid):
                warnings.append(f"Card {idx}: JSON-LD entry {ld['position']} has product {ld_key}, grid says {card_pid}; JSON-LD ignored for this card")
                ld = None
        name = _field(card, "data-name", "h2, h3, [data-testid='product-name']") or (ld["name"] if ld else None)
        url = _field(card, "data-url") or (ld["url"] if ld else None)
        if not url:
            link = card.select_one("a[href]")
            url = link.get("href") if link else None
        if url:
            url = urljoin("https://www.ajio.com/", url)
        pid = _field(card, "data-product-id") or product_key(url)
        image_url = _field(card, "data-image") or (ld["image"] if ld else None)
        if not image_url:
            img = card.select_one("img[src], img[data-src]")
            if img:
                image_url = img.get("src") or img.get("data-src")
                if image_url:
                    image_url = urljoin("https://www.ajio.com/", image_url)

        # SB brand units may legitimately lack a product ID/URL. Product units must be identifiable.
        if not name:
            warnings.append(f"Card {idx} skipped: product name missing")
            rejected.append(RejectedCard(idx, "card_missing_name", "product name missing", _card_payload(card)))
            continue
        if product_type != "SB" and not (pid or url):
            warnings.append(f"Card {idx} skipped: product has neither ID nor URL")
            rejected.append(RejectedCard(idx, "card_missing_identity", "product has neither ID nor URL", _card_payload(card)))
            continue

        units.append(ProductUnit(
            product_type=product_type,
            product_name=name,
            product_url=url,
            product_id=pid,
            sp=parse_price(_field(card, "data-price", "[data-testid='selling-price']")),
            mrp=parse_price(_field(card, "data-mrp", "[data-testid='mrp']")),
            rating=parse_rating(_field(card, "data-rating", "[data-testid='rating']")),
            num_of_rating=parse_count(_field(card, "data-rating-count", "[data-testid='rating-count']")),
            tag=_field(card, "data-tag") or "",
            deal=_field(card, "data-deal") or "",
            product_image_u=image_url,
            campaign_id=_field(card, "data-campaign-id"),
        ))

    if not units:
        return ParseResult("parse_failed", reason="Product grid had cards, but none passed basic validation", warnings=warnings, rejected=rejected)
    return ParseResult("ok", units=units, warnings=warnings, total_items=total_items, rejected=rejected)
