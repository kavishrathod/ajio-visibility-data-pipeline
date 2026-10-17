"""Lightweight data-quality checks and placement-level deduplication."""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Iterable

from src.parsers.product_parser import ProductUnit


def _identity(value: ProductUnit) -> str:
    return value.product_id or value.product_url or re.sub(r"\s+", " ", (value.product_name or "").strip().lower())


def deduplicate_units(units: Iterable[ProductUnit]) -> tuple[list[ProductUnit], int]:
    """Remove repeated placements but keep the same product shown as SP and Organic separate."""
    unique: list[ProductUnit] = []
    seen: set[tuple[str, str, str | None]] = set()
    duplicate_count = 0
    for unit in units:
        key = (unit.product_type, _identity(unit), unit.campaign_id if unit.product_type in {"SP", "SB"} else None)
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        unique.append(unit)
    return unique, duplicate_count


def validate_unit(unit: ProductUnit) -> list[str]:
    errors: list[str] = []
    if not unit.product_name or not unit.product_name.strip():
        errors.append("missing_product_name")
    if unit.product_type not in {"Organic", "SP", "SB"}:
        errors.append("invalid_product_type")
    if unit.rating is not None and not 0 <= unit.rating <= 5:
        errors.append("rating_out_of_range")
    if unit.num_of_rating is not None and unit.num_of_rating < 0:
        errors.append("negative_rating_count")
    return errors


def validate_units(units: Iterable[ProductUnit]) -> tuple[list[ProductUnit], list[dict[str, object]]]:
    accepted: list[ProductUnit] = []
    rejected: list[dict[str, object]] = []
    for unit in units:
        errors = validate_unit(unit)
        if errors:
            rejected.append({"product_name": unit.product_name, "errors": errors})
        else:
            accepted.append(unit)
    deduped, duplicates = deduplicate_units(accepted)
    if duplicates:
        rejected.extend({"errors": ["duplicate_placement_dropped"]} for _ in range(duplicates))
    return deduped, rejected


def placement_key(unit: ProductUnit) -> tuple[str, str, str | None]:
    """Stable placement key: type + product identity (never the title alone) + campaign for paid units."""
    return (unit.product_type, _identity(unit), unit.campaign_id if unit.product_type in {"SP", "SB"} else None)


def validate_entries(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate and deduplicate page entries; return (accepted entries, rejections with reasons).

    Same decisions as ``validate_units`` (validation errors first, then first-occurrence-wins placement
    dedupe), but each rejection keeps the entry and a machine-readable reason so it can be quarantined.
    A rejection is ``{"entry", "stage", "reason_code", "detail"}``; ``stage`` is ``validate`` or ``dedupe``.
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    kept_by_key: dict[tuple[str, str, str | None], dict] = {}
    for entry in entries:
        unit = entry["unit"]
        errors = validate_unit(unit)
        if errors:
            for code in errors:
                rejected.append({"entry": entry, "stage": "validate", "reason_code": code, "detail": f"failed validation rule {code}"})
            continue
        key = placement_key(unit)
        kept = kept_by_key.get(key)
        if kept is not None:
            kept_page, this_page = int(kept["page_number"]), int(entry["page_number"])
            code = "duplicate_placement" if kept_page == this_page else "cross_page_duplicate"
            rejected.append({
                "entry": entry, "stage": "dedupe", "reason_code": code,
                "detail": f"same placement already kept from page {kept_page}; repeated on page {this_page}",
            })
            continue
        kept_by_key[key] = entry
        accepted.append(entry)
    return accepted, rejected


def find_cross_page_duplicates(entries: list[dict]) -> list[dict]:
    """Detect the same placement shown on more than one result page (pagination drift, I-4).

    ``entries`` are in display order and carry ``unit`` and ``page_number``.
    The first occurrence is the one that is kept (see DECISIONS.md); the later
    one is reported so the anomaly can be logged and stored.
    """
    first_seen: dict[tuple[str, str, str | None], int] = {}
    anomalies: list[dict] = []
    for entry in entries:
        key = placement_key(entry["unit"])
        page = int(entry["page_number"])
        if key in first_seen and first_seen[key] != page:
            anomalies.append({
                "product_id": key[1], "product_type": key[0],
                "kept_on_page": first_seen[key], "repeated_on_page": page,
            })
        else:
            first_seen.setdefault(key, page)
    return anomalies
