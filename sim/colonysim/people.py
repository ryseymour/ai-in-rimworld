"""Population: how many people a colony has, and what food does to that.

Until now a colony's population was a number set at founding and never looked
at again. It decided how much the colony ate and, through the land, how much it
made, and then it sat there. Nothing the economy did could change it, which
meant nothing the economy did had any stakes: a colony that ran out of food
simply went without, indefinitely, and a colony swimming in it was no better
off for that.

This makes it a live quantity, on one rule: **people follow food.**

* A colony with a full granary and more coming in grows. Not quickly -- a
  season of plenty is a few percent, not a boom.
* A colony that cannot feed everyone loses people, and fast. Some starve, and
  the ones who can walk go somewhere that can feed them.
* A colony whose stores are merely thin loses a trickle to the same instinct,
  before anyone actually goes hungry.

Two couplings make that matter to the rest of the sim. Eating is per head, so
more people is more demand and a deeper granary to fill. Making things is
**not** per head: the land a village works is fixed, so doubling the people
does not double the harvest (`LAND_ELASTICITY`). That is the ceiling. A colony
grows into its own land and then stops, and the only way past it is to buy food
from somewhere with land to spare -- which is the whole point of the roads.

The other coupling is who is available to walk them. A caravan is people, and
guards are more people, and a colony will not have more than `ROAD_SHARE` of
itself away from home at once. So a colony that has grown can run two caravans,
or run one and guard it; a colony that has shrunk can do neither.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .goods import GOODS

if TYPE_CHECKING:  # pragma: no cover - import only for the annotation
    from .storage import Colony

#: How far the land's output follows the number of people working it. At 1.0
#: twice the people would mean twice the harvest and a colony could grow
#: forever; at 0 the land gives what it gives however many work it. In between
#: is the interesting case: more hands help, but less each time.
LAND_ELASTICITY = 0.7

#: Food cover -- what is on the shelves as a fraction of the food buffer --
#: above which a colony is comfortable enough to grow, and below which people
#: start looking elsewhere. Between them nothing happens, so an ordinary
#: colony's population is steady rather than permanently drifting.
PLENTY = 1.15
LEAN = 0.65

#: Fastest a well-stocked colony grows, per day. Deliberately slow: at full
#: tilt this is about a fifth over a 150-day run, so growth is something you
#: notice across a season rather than a number that runs away.
BIRTH_RATE = 0.0026
#: How much of its stores above `PLENTY` it takes to grow at that rate. Half a
#: granary again, so a colony has to be genuinely comfortable, not just fed.
PLENTY_SPAN = 0.5

#: Fastest a colony loses people to hunger, per day, with nothing at all to
#: eat. A colony in complete famine is down a tenth in a week: bad enough to
#: be a crisis, slow enough that a caravan can still get there in time.
HUNGER_RATE = 0.016
#: ...and to people walking out because the stores look thin. A tenth of the
#: hunger rate: leaving is what you do before it gets bad.
LEAVING_RATE = 0.0016

#: Weight on the remembered ration when judging how well fed a colony is. About
#: a fortnight, so one empty day is not a famine and one delivery is not a
#: recovery.
RATION_MEMORY = 0.9

#: A colony never quite goes to nothing. Something is always left to build back
#: from, and an empty colony would only be a division by zero looking for
#: somewhere to happen.
MIN_POPULATION = 4.0

#: Most of itself a colony will have away from home at once.
ROAD_SHARE = 0.22
#: People to run one caravan, and the extra hands it takes to escort one.
CREW = 3.0
GUARDS = 2.0


@dataclass(frozen=True)
class Change:
    """What one day did to a colony's population."""

    before: float
    after: float
    born: float = 0.0
    starved: float = 0.0
    left: float = 0.0

    @property
    def net(self) -> float:
        return self.after - self.before


def food_cover(colony: "Colony") -> float:
    """Food on the shelves as a fraction of the buffer the good asks for.

    Measured against the good's own buffer rather than the colony's current
    reserve, the same way the steward measures it: a colony that had just
    raised its reserve would otherwise read as hungrier for having decided to
    be careful.
    """
    rate = colony.consumption.get("food", 0.0)
    days = GOODS["food"].buffer_days
    if rate <= 0 or days <= 0:
        return float("inf")
    return colony.storage.get("food") / (rate * days)


def step(colony: "Colony", ration: float) -> Change:
    """One day of births, hunger and departures.

    `ration` is the share of today's food demand the colony actually got off
    its own shelves -- 1.0 when everyone ate, 0.0 when the granary was empty.
    It is smoothed into `colony.nourishment` before anything is decided, so the
    population answers to how the last fortnight went rather than to today.
    """
    colony.nourishment = (
        RATION_MEMORY * colony.nourishment + (1.0 - RATION_MEMORY) * clamp01(ration)
    )
    before = colony.population
    cover = food_cover(colony)

    born = starved = left = 0.0
    hunger = max(0.0, 1.0 - colony.nourishment)
    if hunger > 0.0:
        starved = before * HUNGER_RATE * hunger
    if cover < LEAN:
        left = before * LEAVING_RATE * ((LEAN - cover) / LEAN)
    elif cover > PLENTY and colony.nourishment > 0.98:
        # Fed, and with stores to spare. Only then.
        plenty = min(1.0, (cover - PLENTY) / PLENTY_SPAN)
        born = before * BIRTH_RATE * plenty

    after = max(MIN_POPULATION, before + born - starved - left)
    # What the floor refused to take is not a death; say so, so the tallies
    # still add up to the population.
    refused = after - (before + born - starved - left)
    if refused > 0.0:
        taken = starved + left
        if taken > 0.0:
            starved -= refused * (starved / taken)
            left -= refused * (left / taken)

    colony.resize(after)
    colony.born += born
    colony.starved += starved
    colony.left += left
    return Change(before=before, after=after, born=born, starved=starved, left=left)


def hands(population: float) -> float:
    """How many people a colony is willing to have away from home at once."""
    return population * ROAD_SHARE


def caravans_allowed(population: float) -> int:
    """How many caravans this many people can crew at the same time.

    Always at least one: a village that has shrunk to nothing still sends
    someone to fetch food, and a colony locked out of trading by its own
    smallness could never trade its way back.
    """
    return max(1, int(hands(population) // CREW))


def can_escort(population: float, caravans_out: int) -> bool:
    """Whether there are hands to spare to guard a caravan.

    Counting the caravan being sent, so a colony really is choosing between a
    second cart on the road and guards on the first.
    """
    return hands(population) - caravans_out * CREW >= GUARDS


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
