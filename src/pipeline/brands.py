"""Brand normalisation.

A brand is only ever taken from an explicit field on the page (``data-brand`` on a card, or the brand label a card
shows). It is never inferred from the product title, because a title prefix is not a validated brand: titles such as
"7 Alt by Pantaloons Men Cotton Relaxed Fit Kurta" or "Men Lace-Up Sneakers" do not follow one rule.

Two values are kept: ``brand`` (cleaned text for display) and ``brand_key`` (a stable grouping key). Variants that
differ only in case, spacing or Unicode form share a key. Anything else that should be treated as the same brand
(for example "U.S. Polo Assn." and "US Polo Assn") is listed by hand in ``config/brand_aliases.json``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

MAX_BRAND_LENGTH = 80
# Values a page shows when it has no brand. They are not brands, so they become NULL rather than a "brand".
PLACEHOLDERS = frozenset({"n/a", "na", "none", "null", "nil", "unknown", "undefined", "not available", "-", "--", "—"})


def clean_brand(raw: object) -> Optional[str]:
    """Display text for a brand, or None when the field is empty, a placeholder, or implausibly long."""
    if raw is None:
        return None
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(raw))).strip()
    if not text or text.casefold() in PLACEHOLDERS or len(text) > MAX_BRAND_LENGTH:
        return None
    if not re.search(r"[^\W_]", text):          # punctuation only
        return None
    return text


def brand_key(display: Optional[str]) -> Optional[str]:
    """Grouping key: case-folded, punctuation and spacing collapsed (``&`` is kept: it distinguishes H&M from HM)."""
    cleaned = clean_brand(display)
    if cleaned is None:
        return None
    key = re.sub(r"[^\w&]+", " ", cleaned.casefold()).strip()
    return key or None


def normalize_brand(raw: object, aliases: Optional[dict[str, str]] = None) -> tuple[Optional[str], Optional[str]]:
    """Return ``(brand, brand_key)``. ``aliases`` maps a variant's key to the canonical display name."""
    display = clean_brand(raw)
    key = brand_key(display)
    if key is None:
        return None, None
    canonical = (aliases or {}).get(key)
    if canonical:
        return canonical, brand_key(canonical)
    return display, key


def load_brand_aliases(root: str | Path) -> dict[str, str]:
    """Read ``config/brand_aliases.json`` (optional). Returns ``{variant key: canonical display name}``."""
    path = Path(root) / "config" / "brand_aliases.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("aliases", {})
    if not isinstance(entries, dict):
        raise ValueError("config/brand_aliases.json: 'aliases' must be an object of variant -> canonical brand")
    aliases: dict[str, str] = {}
    for variant, canonical in entries.items():
        variant_key, canonical_display = brand_key(variant), clean_brand(canonical)
        if variant_key is None or canonical_display is None:
            raise ValueError(f"config/brand_aliases.json: invalid alias {variant!r} -> {canonical!r}")
        aliases[variant_key] = canonical_display
    return aliases
