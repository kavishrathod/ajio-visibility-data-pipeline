"""Value parsing helpers (I-5) and product key extraction (I-6).

TODO: implement parse_page(raw: RawResponse) -> ParseResult
  - HTTP 200 + grid container missing/renamed -> status="parse_failed" (I-1), never zero_result
  - valid "no products" marker               -> status="zero_result" (I-2)
"""
from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urlsplit

_PRODUCT_RE = re.compile(r"/p/(\d+)(?:_([A-Za-z0-9-]+))?")


def parse_price(text: Optional[str]) -> Optional[str]:
    """'₹1,299' / 'Rs. 1299.00' -> '1299.00'. Range or junk -> None. Never 0 for missing."""
    if not text:
        return None
    t = text.strip()
    if re.search(r"\d\s*[-–to]+\s*(₹|rs\.?)?\s*\d", t, re.I):  # ranges: ambiguous, decide in DECISIONS.md
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", t)
    if not m:
        return None
    try:
        return f"{Decimal(m.group(1).replace(',', '')):.2f}"
    except InvalidOperation:
        return None


def parse_count(text: Optional[str]) -> Optional[int]:
    """'1.2K' -> 1200, '(1,234)' -> 1234, missing -> None."""
    if not text:
        return None
    t = text.strip().strip("()").replace(",", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmM]?)", t)
    if not m:
        return None
    n = float(m.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()]
    return int(round(n))


def product_key(url: Optional[str]) -> Optional[str]:
    """Stable key from the URL path, ignoring tracking params. Never the title."""
    if not url:
        return None
    m = _PRODUCT_RE.search(urlsplit(url).path)
    if not m:
        return None
    return f"{m.group(1)}_{m.group(2)}" if m.group(2) else m.group(1)
