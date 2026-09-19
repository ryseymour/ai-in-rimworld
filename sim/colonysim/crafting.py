"""The workshop: a colony turning materials and labour into goods.

Three things make this more than a conversion table:

* **It only ever works with what the colony can spare.** Every recipe draws on
  surplus -- stock above the reserve -- exactly as barter does, so a colony can
  never whittle its way into a famine. A village whose wood is down to its own
  buffer stops fletching until the woodcutters catch up.
* **It has to want the thing.** What gets made is what the colony is short of,
  plus what the markets it has actually seen were short of and paying more for
  than home. So a forest village with a neighbour crying out for bows makes
  bows, and stops when the neighbour is supplied.
* **A hand gets better.** Skill rises with the labour that goes through the
  bench and shortens the work; recipes have a floor below which the colony
  simply cannot make the thing, so a workshop has somewhere to get to. A smithy
  is the one building in the sim, and a colony has to decide to put it up.

Crafted goods are ordinary goods -- `goods.py` prices them off these recipes
and `GOOD_NAMES` carries them -- so a bow sits on the same shelf as food, is
priced by the same scarcity, rides in the same caravan and can be handed over
as barter. Nothing in the trade code needed to know crafting exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .goods import GOODS
from .recipes import RECIPES, STATIONS, STARTING_STATIONS, Recipe

if TYPE_CHECKING:  # pragma: no cover - import for types only, and one-way
    from .storage import Colony

#: Labour-days a colony gives its workbenches per head per day. Small: most of
#: a village is in the fields, and the bench is what is left over.
CRAFT_LABOUR_PER_CAPITA = 0.06

#: The hand a colony starts with, what a labour-day at the bench adds to it,
#: and how much longer the work takes at no skill than at a practised one.
SKILL_START = 0.25
SKILL_GAIN = 0.003
SLOW_HANDS = 1.8

#: How much of a foreign shortfall a colony will make for export. Below one
#: because the news is old and somebody else may already be on the road there.
EXPORT_KEENNESS = 0.6

#: The most of a material's spare stock the bench will get through in one day.
#: Surplus is a pile, not a daily rate, and a workshop that ground the whole
#: pile into arrows the day it appeared would leave a colony nothing to trade
#: with, nothing to build with and no reason ever to stop fletching.
MATERIAL_SHARE = 0.4

#: What each weapon is worth to a colony defending a caravan, and how many
#: weighted weapons per head count as properly armed. Bows do it best; a club
#: is better than empty hands.
WEAPON_WEIGHT = {"bow": 1.0, "spear": 0.8, "knife": 0.5, "club": 0.4}
ARMED_FULL = 0.35

#: What wears out per head per day. For a weapon this is breakage: the rate,
#: times the good's service life in `goods.CRAFTED_SPECS`, is about the armoury
#: a colony of that size keeps. Arrows are not here -- they are spent hunting,
#: and `hunting.py` sets that rate.
WEAR_PER_CAPITA = {
    "club": 0.0004,
    "spear": 0.000333,
    "bow": 0.000375,
    "knife": 0.000417,
}


def work_for(recipe: Recipe, skill: float) -> float:
    """Labour-days one batch actually takes at this hand."""
    hand = max(0.0, min(1.0, skill))
    return recipe.work * (SLOW_HANDS - (SLOW_HANDS - 1.0) * hand)


@dataclass
class Workshop:
    """A colony's benches, its hand at them, and what it is putting up."""

    stations: set[str] = field(default_factory=lambda: set(STARTING_STATIONS))
    skill: float = SKILL_START
    #: Batches finished and labour-days spent, for the display and for tests
    #: that want to know the bench ran at all.
    batches: float = 0.0
    labour_spent: float = 0.0
    #: The bench being raised, what has been gathered for it, and how far the
    #: work has got. Materials go in as the colony can spare them, so a stone
    #: village has a smithy in a fortnight and a forest one waits on a caravan.
    raising: str = ""
    gathered: dict[str, float] = field(default_factory=dict)
    progress: float = 0.0
    #: What came off the bench today, for the viewer.
    making: tuple[str, ...] = ()

    def can_make(self, recipe: Recipe) -> bool:
        return recipe.station in self.stations and self.skill >= recipe.skill

    def recipes(self) -> list[Recipe]:
        """Everything this workshop could make today, if it wanted to."""
        return [r for r in RECIPES.values() if self.can_make(r)]

    def practise(self, labour: float) -> None:
        self.labour_spent += labour
        self.skill = min(1.0, self.skill + SKILL_GAIN * labour)

    def owed(self) -> dict[str, float]:
        """Materials a bench being raised still needs."""
        if not self.raising:
            return {}
        return {
            good: qty - self.gathered.get(good, 0.0)
            for good, qty in STATIONS[self.raising].cost.items()
            if qty - self.gathered.get(good, 0.0) > 1e-9
        }

    def describe(self) -> str:
        benches = ", ".join(sorted(self.stations))
        out = f"{benches}, hand {self.skill:.2f}"
        if self.making:
            out += ", making " + ", ".join(self.making)
        if self.raising:
            station = STATIONS[self.raising]
            owed = self.owed()
            if owed:
                out += f", gathering {', '.join(sorted(owed))} for a {self.raising}"
            else:
                done = self.progress / station.work if station.work else 1.0
                out += f", raising a {self.raising} ({done:.0%})"
        return out


# --------------------------------------------------------------- what to make


def want(colony: "Colony", good: str) -> float:
    """How many more of a good the colony would like made.

    Its own shortfall first -- that is the arrows its hunters have shot and the
    axe that broke. Then whatever the best market it has actually visited was
    short of, but only where that market was paying more for it than home,
    since otherwise there is no trip in it. Times whatever its steward has said
    about this good, and less whatever is already spare on the shelves: a
    village with ten bows in the rack and one neighbour wanting two does not
    need an eleventh. Without that last term a workshop makes for a demand it
    has already met, which for a durable thing like a weapon means making them
    forever.
    """
    keen = colony.policy.craft_for(good)
    if keen <= 0.0:
        return 0.0
    here = colony.price(good)
    abroad = max(
        (
            view.shortfall.get(good, 0.0)
            for view in colony.known.values()
            if view.prices.get(good, 0.0) > here
        ),
        default=0.0,
    )
    wanted = (colony.shortfall(good) + EXPORT_KEENNESS * abroad) * keen
    return max(0.0, wanted - colony.surplus(good))


def batches_possible(colony: "Colony", recipe: Recipe) -> float:
    """How many batches the materials the colony can spare would cover today.

    Only surplus, and only a share of it, so the pile a bench works from
    refills rather than being consumed the day it appears.
    """
    if not recipe.inputs:
        return float("inf")
    return min(
        colony.surplus(good) * MATERIAL_SHARE / qty
        for good, qty in recipe.inputs.items()
    )


def order_of_work(colony: "Colony") -> list[Recipe]:
    """What the bench turns to first: the best coin per labour-day it can earn.

    Scarcity is already in the price, so a colony out of arrows finds fletching
    at the top of the list without anything saying "arrows are urgent".
    """
    shop = colony.workshop
    scored: list[tuple[float, str, Recipe]] = []
    for recipe in shop.recipes():
        if want(colony, recipe.output) <= 0.0:
            continue
        per_batch = work_for(recipe, shop.skill)
        if per_batch <= 0.0:
            continue
        earned = colony.price(recipe.output) * recipe.quantity
        scored.append((earned / per_batch, recipe.output, recipe))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [recipe for _, _, recipe in scored]


# ------------------------------------------------------------------ the day


def make(
    colony: "Colony",
    recipe: Recipe,
    labour: float,
    made: dict[str, float],
    used: dict[str, float],
) -> float:
    """Run one recipe as far as labour, materials and demand allow.

    Returns the labour-days spent. Batches are fractional, like every other
    rate in the sim: half a batch of arrows is five arrows, and a colony that
    can only spare an hour still gets an hour's work done.
    """
    shop = colony.workshop
    per_batch = work_for(recipe, shop.skill)
    wanted = want(colony, recipe.output)
    if wanted <= 0.0 or per_batch <= 0.0:
        return 0.0

    batches = min(
        labour / per_batch,
        wanted / recipe.quantity,
        batches_possible(colony, recipe),
    )
    if batches <= 1e-9:
        return 0.0

    for good, qty in recipe.inputs.items():
        took = colony.storage.remove(good, qty * batches)
        used[good] = used.get(good, 0.0) + took
    out = recipe.quantity * batches
    colony.storage.add(recipe.output, out)
    made[recipe.output] = made.get(recipe.output, 0.0) + out

    spent = per_batch * batches
    shop.practise(spent)
    shop.batches += batches
    return spent


def raise_station(colony: "Colony", labour: float, used: dict[str, float]) -> float:
    """Put up whatever bench the colony has decided it wants.

    Materials are gathered out of surplus at the same pace anything else is,
    so a colony short of stone spends weeks collecting it and goes on making
    what it can meanwhile. Once the pile is there the build takes the bench's
    whole day until it is done -- a colony building somewhere to make things is
    not making things.

    Returns the labour left over.
    """
    shop = colony.workshop
    if not shop.raising or shop.raising in shop.stations:
        shop.raising = ""
        return labour
    station = STATIONS[shop.raising]

    owed = shop.owed()
    if owed:
        for good, need in owed.items():
            got = colony.storage.remove(
                good, min(need, colony.surplus(good) * MATERIAL_SHARE)
            )
            if got > 0.0:
                shop.gathered[good] = shop.gathered.get(good, 0.0) + got
                used[good] = used.get(good, 0.0) + got
        return labour  # still short; the bench gets on with something else

    spend = min(labour, max(0.0, station.work - shop.progress))
    shop.progress += spend
    shop.practise(spend)
    if shop.progress >= station.work:
        shop.stations.add(station.name)
        shop.raising = ""
        shop.gathered = {}
        shop.progress = 0.0
    return labour - spend


def work_day(colony: "Colony") -> tuple[dict[str, float], dict[str, float]]:
    """One day at the benches. Returns what was made and what it was made of.

    Both halves go back to the simulation's own totals, which is what keeps
    conservation honest: crafting destroys materials and creates goods, and
    every unit of each is counted.
    """
    shop = colony.workshop
    made: dict[str, float] = {}
    used: dict[str, float] = {}
    labour = max(0.0, colony.population * CRAFT_LABOUR_PER_CAPITA)

    labour = raise_station(colony, labour, used)
    for recipe in order_of_work(colony):
        if labour <= 1e-9:
            break
        labour -= make(colony, recipe, labour, made, used)

    shop.making = tuple(sorted(made))
    return made, used


# ---------------------------------------------------------------- being armed


def armed_strength(colony: "Colony") -> float:
    """How well armed the colony's own people are, 0 to 1.

    What it buys is on the road: a caravan out of an armed colony is harder for
    animals to bother, and the guards it hires cost less because half the job
    is already done. That is the loop the weapons close -- a colony crafts
    spears, and the wolves become someone else's problem.
    """
    if colony.population <= 0:
        return 0.0
    weighted = sum(
        colony.storage.get(good) * weight for good, weight in WEAPON_WEIGHT.items()
    )
    return max(0.0, min(1.0, weighted / (colony.population * ARMED_FULL)))


def armoury(colony: "Colony") -> dict[str, float]:
    """What the colony has to fight or hunt with, for display."""
    return {
        good: colony.storage.get(good)
        for good in WEAPON_WEIGHT
        if good in GOODS and colony.storage.get(good) > 0.05
    }
