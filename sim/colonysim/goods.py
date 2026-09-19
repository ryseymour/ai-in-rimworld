"""The goods colonies make, eat, and trade."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Good:
    """`buffer_days` is how much of its own consumption a colony holds back
    before it will sell any: the reserve. `bulk` is cargo space per unit."""

    name: str
    base_price: float
    buffer_days: float
    bulk: float = 1.0


GOODS: dict[str, Good] = {
    g.name: g
    for g in (
        Good("food", base_price=2.0, buffer_days=20.0, bulk=1.0),
        Good("wood", base_price=1.0, buffer_days=12.0, bulk=1.4),
        Good("stone", base_price=1.3, buffer_days=10.0, bulk=2.0),
        Good("cloth", base_price=4.5, buffer_days=25.0, bulk=0.6),
        Good("tools", base_price=9.0, buffer_days=40.0, bulk=0.8),
    )
}

GOOD_NAMES = tuple(GOODS)
