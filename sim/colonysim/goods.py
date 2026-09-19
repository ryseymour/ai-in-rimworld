"""The goods colonies make, eat, craft and trade."""
from __future__ import annotations

from dataclasses import dataclass

from .recipes import RECIPES, derived_price


@dataclass(frozen=True)
class Good:
    """`buffer_days` is how much of its own consumption a colony holds back
    before it will sell any: the reserve. `bulk` is cargo space per unit."""

    name: str
    base_price: float
    buffer_days: float
    bulk: float = 1.0


RAW_GOODS: dict[str, Good] = {
    g.name: g
    for g in (
        Good("food", base_price=2.0, buffer_days=20.0, bulk=1.0),
        Good("wood", base_price=1.0, buffer_days=12.0, bulk=1.4),
        Good("stone", base_price=1.3, buffer_days=10.0, bulk=2.0),
        Good("cloth", base_price=4.5, buffer_days=25.0, bulk=0.6),
        Good("tools", base_price=9.0, buffer_days=40.0, bulk=0.8),
    )
}
"""What the land itself gives. Every one of these has a terrain that is good at
it, which is what makes colonies unequal and trade worth doing."""

#: The crafted goods, as cargo and as something a colony keeps: how much space
#: a unit takes, and how many days of its own use a colony holds back. For a
#: weapon that second number is its service life, so the reserve works out at
#: roughly the armoury a colony of that size wants; for arrows it is a month's
#: shooting, because arrows are spent rather than kept.
CRAFTED_SPECS: dict[str, tuple[float, float]] = {
    "club": (1.2, 500.0),
    "spear": (1.6, 450.0),
    "arrows": (0.15, 25.0),
    "bow": (1.0, 400.0),
    "knife": (0.3, 600.0),
}

GOODS: dict[str, Good] = dict(RAW_GOODS)
# Priced off their own recipes: materials plus the work in them. Raw goods that
# also have a recipe -- tools -- keep the price the land put on them, so making
# them is a choice against buying or digging rather than a free win.
for _name, (_bulk, _buffer) in CRAFTED_SPECS.items():
    GOODS[_name] = Good(
        _name,
        base_price=derived_price(RECIPES[_name], lambda g: GOODS[g].base_price),
        buffer_days=_buffer,
        bulk=_bulk,
    )

CRAFTED_GOOD_NAMES = tuple(CRAFTED_SPECS)
"""Goods that exist only because somebody made them."""

RAW_GOOD_NAMES = tuple(RAW_GOODS)
"""Goods the land gives, and so the only ones a colony's terrain produces."""

GOOD_NAMES = tuple(GOODS)
"""Everything that can sit on a shelf or ride in a caravan. Crafted goods are
in here with the rest on purpose: one set of prices, one storage building, one
kind of cargo, so a bow trades exactly the way food does."""
