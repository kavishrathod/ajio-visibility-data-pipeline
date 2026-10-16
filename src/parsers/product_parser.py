"""Parse synthetic/static product-grid HTML and normalize messy values.

The parser deliberately distinguishes a valid no-results marker from an absent
or renamed grid. It is not an assertion about AJIO's actual current page DOM.
"""
from __future__ import annotations

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
class ParseResult:
    status: str  # ok | zero_result | parse_failed | blocked
    units: list[ProductUnit] = field(default_factory=list)
    reason: str = ""
    warnings: list[str] = field(default_factory=list)


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


def parse_products(body: str, http_status: int = 200) -> ParseResult:
    """Parse one HTML page into a typed outcome; HTTP status is checked first."""
    if http_status in {401, 403, 429}:
        return ParseResult("blocked", reason=f"HTTP {http_status}; no parser retry/bypass attempted")
    if http_status >= 400:
        return ParseResult("parse_failed", reason=f"Unexpected HTTP status {http_status}")

    soup = BeautifulSoup(body or "", "html.parser")
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
    warnings: list[str] = []
    for idx, card in enumerate(cards, start=1):
        name = _field(card, "data-name", "h2, h3, [data-testid='product-name']")
        raw_kind = (_field(card, "data-kind") or "ORGANIC").strip().upper()
        product_type = raw_kind if raw_kind in {"SP", "SB"} else "Organic"
        url = _field(card, "data-url")
        if not url:
            link = card.select_one("a[href]")
            url = link.get("href") if link else None
        if url:
            url = urljoin("https://www.ajio.com/", url)
        pid = _field(card, "data-product-id") or product_key(url)
        image_url = _field(card, "data-image")
        if not image_url:
            img = card.select_one("img[src], img[data-src]")
            if img:
                image_url = img.get("src") or img.get("data-src")
                if image_url:
                    image_url = urljoin("https://www.ajio.com/", image_url)

        # SB brand units may legitimately lack a product ID/URL. Product units must be identifiable.
        if not name:
            warnings.append(f"Card {idx} skipped: product name missing")
            continue
        if product_type != "SB" and not (pid or url):
            warnings.append(f"Card {idx} skipped: product has neither ID nor URL")
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
        return ParseResult("parse_failed", reason="Product grid had cards, but none passed basic validation", warnings=warnings)
    return ParseResult("ok", units=units, warnings=warnings)
