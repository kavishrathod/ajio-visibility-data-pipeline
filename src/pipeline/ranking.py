"""Rank assignment; ranks continue across pages within one keyword-hour slot."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RankState:
    absolute: int = 0
    per_type: dict[str, int] = field(default_factory=dict)


def assign_ranks(product_types: list[str], state: RankState | None = None):
    state = state or RankState()
    absolute = state.absolute
    per_type = dict(state.per_type)
    result = []
    for product_type in product_types:
        absolute += 1
        per_type[product_type] = per_type.get(product_type, 0) + 1
        result.append((absolute, per_type[product_type]))
    return result, RankState(absolute, per_type)
