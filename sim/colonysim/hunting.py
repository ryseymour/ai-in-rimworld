"""Hunting: what a colony gets for having bows and arrows, and what it costs.

Arrows are the sim's measure of hunting effort. A colony's hunters loose a
steady number of them a day, which is why arrows are the one crafted good a
colony spends rather than keeps, and why fletching never finishes. What that
effort brings home depends on what the party is carrying: with a bow each they
come back with meat and hides, and with no bows between them the same days in
the woods yield snares and thrown spears and very little else.

What a colony hunts is deer and boar, not the wolves and bears of
`wildlife.py` -- those are predators, and a caravan meeting one is a different
event entirely -- so nothing here depends on where the dens are. `cloth`
carries the hides, the same way it carries fleece in `wildlife.PREY`.

The point of the whole loop is that it is a second way to be fed. A colony with
a forest, a fletcher and a few bows turns wood into meat without waiting for a
caravan, which is exactly the independence a weapon is for; it is a supplement
to the fields rather than a replacement, so a village that cannot farm still
cannot live on hunting alone.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import for types only
    from .storage import Colony

#: Arrows loosed per head per day, and the share of a colony out hunting. Set
#: so a hunting party shoots a month's worth of arrows in about a month, which
#: is what makes arrows a running demand rather than a one-off purchase.
ARROWS_PER_CAPITA = 0.07
HUNTER_SHARE = 0.2

#: Food off one arrow, with a bow in every hunter's hands and with none. A
#: hunting party of four brings in a few days' food a week at best: enough to
#: matter to a colony that is short, not enough to feed one that cannot farm.
MEAT_PER_ARROW = 0.8
MEAT_PER_ARROW_UNARMED = 0.25
#: Hides, which the economy already calls cloth.
HIDES_PER_ARROW = 0.08


def hunters(colony: "Colony") -> float:
    return max(0.0, colony.population * HUNTER_SHARE)


def bow_coverage(colony: "Colony") -> float:
    """The share of the hunting party that has a bow to hunt with."""
    party = hunters(colony)
    if party <= 0.0:
        return 0.0
    return max(0.0, min(1.0, colony.storage.get("bow") / party))


def meat_per_arrow(colony: "Colony") -> float:
    coverage = bow_coverage(colony)
    return MEAT_PER_ARROW_UNARMED + (MEAT_PER_ARROW - MEAT_PER_ARROW_UNARMED) * coverage


def hunt(colony: "Colony", arrows: float) -> dict[str, float]:
    """Spend a day's arrows and put what came back on the shelves.

    `arrows` is what the colony's own consumption already took off the shelves,
    so nothing is taken here -- this is only what the shooting was worth. A
    colony out of arrows brings home nothing, which is the whole reason a
    village wants a fletcher.
    """
    if arrows <= 0.0:
        return {}
    bag = {
        "food": arrows * meat_per_arrow(colony),
        "cloth": arrows * HIDES_PER_ARROW,
    }
    for good, qty in bag.items():
        colony.storage.add(good, qty)
    return bag
