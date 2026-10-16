"""Rank assignment. Pure function, matches the brief's worked example."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RankState:
    """Carry this across pages so ranks are continuous."""
    absolute: int = 0
    per_type: dict = field(default_factory=dict)


def assign_ranks(product_types: list[str], state: RankState | None = None):
    """product_types in top-to-bottom order. Returns ([(abs, rel), ...], new_state)."""
    state = state or RankState()
    out = []
    abs_n = state.absolute
    per = dict(state.per_type)
    for t in product_types:
        abs_n += 1
        per[t] = per.get(t, 0) + 1
        out.append((abs_n, per[t]))
    return out, RankState(abs_n, per)
