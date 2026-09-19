"""What can be made, out of what, and where: the recipe table.

Data only, and deliberately so. A recipe is a row -- inputs, labour, the bench
it needs, the hand it takes -- so adding one is adding a line rather than
writing code, and nothing in this file knows anything about colonies, storage
or prices. `crafting.py` is the part that does the work.

The set below is the basics, in the spirit of RimWorld's own: a club anyone can
cut from a branch, a spear and a knife for people who have spent some time at
it, and the bow and arrows that turn a colony into one that can feed itself off
the land. Crafted goods trade like any other good, so a village with a good
woodworker and a forest behind it exports bows.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Station:
    """A workbench. `cost` is the materials to put it up, `work` the labour.

    A colony builds one when it wants what the bench makes, which is the only
    thing in the sim that a colony builds -- enough to make a smithy a decision
    rather than a given.
    """

    name: str
    cost: dict[str, float]
    work: float


CRAFTING_SPOT = Station("crafting spot", {}, 0.0)
SMITHY = Station("smithy", {"stone": 30.0, "wood": 8.0}, 10.0)

STATIONS: dict[str, Station] = {s.name: s for s in (CRAFTING_SPOT, SMITHY)}

#: What every colony starts with. A cleared patch of ground and some tools is
#: not a building, so nobody has to earn it.
STARTING_STATIONS = (CRAFTING_SPOT.name,)


@dataclass(frozen=True)
class Recipe:
    """One thing a colony can make.

    `work` is labour-days for the whole batch at a practised hand; a poor one
    takes longer. `skill` is the hand it takes at all -- below it the colony
    simply cannot make the thing yet, which is what gives a workshop somewhere
    to get to.
    """

    output: str
    quantity: float
    inputs: dict[str, float]
    work: float
    station: str = CRAFTING_SPOT.name
    skill: float = 0.0

    @property
    def name(self) -> str:
        return self.output

    def work_per_unit(self) -> float:
        return self.work / self.quantity if self.quantity else self.work


RECIPES: dict[str, Recipe] = {
    r.output: r
    for r in (
        # A length of wood and an afternoon. The weapon of a colony that has
        # nothing else, and the reason nobody is ever completely unarmed.
        Recipe("club", 1.0, {"wood": 6.0}, work=0.6),
        # Wood and a knapped stone head.
        Recipe("spear", 1.0, {"wood": 10.0, "stone": 2.0}, work=1.0, skill=0.1),
        # Ten to a batch, because nobody fletches one arrow.
        Recipe("arrows", 10.0, {"wood": 4.0, "stone": 1.0}, work=0.8, skill=0.15),
        # Cloth is the string. A bow is the difference between a hunting party
        # that comes home with something and one that does not.
        Recipe("bow", 1.0, {"wood": 12.0, "cloth": 2.0}, work=2.2, skill=0.35),
        Recipe("knife", 1.0, {"wood": 4.0, "stone": 6.0}, work=1.2, station=SMITHY.name, skill=0.3),
        # Tools the land also yields, so this is a colony choosing to make more
        # of something it could otherwise only dig for or buy.
        Recipe("tools", 2.0, {"wood": 6.0, "stone": 8.0}, work=2.0, station=SMITHY.name, skill=0.45),
    )
}

#: What a labour-day at a bench is worth in coin, and so what the work in a
#: crafted good adds to its price. Set near a day's food for a couple of
#: people: enough that labour is most of what a weapon costs, which is why
#: crafted goods are worth hauling and raw stone is not.
WORK_VALUE = 2.6


def derived_price(recipe: Recipe, price: Callable[[str], float]) -> float:
    """What a unit of this is worth: its materials, plus the work in it.

    Prices are derived rather than written down so that a new recipe cannot be
    quietly mispriced against the rest of the table. Scarcity still decides
    what any colony actually charges -- this is only the base the whole
    economy measures against.
    """
    materials = sum(qty * price(good) for good, qty in recipe.inputs.items())
    per_batch = materials + recipe.work * WORK_VALUE
    return per_batch / recipe.quantity if recipe.quantity else per_batch
