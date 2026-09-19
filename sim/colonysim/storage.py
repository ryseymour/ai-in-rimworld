"""The storage building, and the colony that owns it.

Storage is the whole trade interface. What a colony will sell is whatever sits
above its reserve; what it will buy is whatever sits below. Prices follow from
the same number. Nothing scripts the economy -- it falls out of what each
colony actually produces and eats.

On top of that sits a `Policy`: the handful of settings a colony's steward
actually controls -- what it adds to or takes off its own prices, how much it
insists on keeping back, and where it puts its people. Scarcity still sets the
shape of every price; the policy is the colony's own stance on top of it. A
colony with a default policy behaves exactly as it did before there were
stewards, which is the control case for every claim about what they do.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .goods import GOOD_NAMES, GOODS
from .money import SILVER, Purse
from .people import LAND_ELASTICITY, MIN_POPULATION
from .world import Settlement

#: Price multiplier bounds. A glut must not drive a price to nothing, and a
#: famine must not make one good worth more than a caravan.
MIN_MULT = 0.35
MAX_MULT = 3.0

#: How far a steward may move its own prices, as a multiple of what scarcity
#: alone would charge. Wide enough to change who trades with whom, narrow
#: enough that a bad steward cannot price its colony out of the world.
MIN_MARKUP = 0.6
MAX_MARKUP = 1.8
#: How far a steward may move the reserve, as a multiple of the good's own
#: buffer days. It can hold back more than two months of food or barely three
#: weeks of it, and no further either way.
MIN_RESERVE = 0.4
MAX_RESERVE = 2.5
#: How far the land's own output can be pushed toward or away from one good.
#: Terrain still decides what a village is good at; this is only how hard it
#: leans on what it has.
MIN_FOCUS = 0.5
MAX_FOCUS = 1.6


#: What a trader assumes about a market it has never visited: ordinary prices
#: and a decent amount both spare and wanted. Optimistic on purpose, so
#: somewhere unvisited is worth a look.
UNKNOWN_SURPLUS = 60.0
UNKNOWN_SHORTFALL = 60.0


@dataclass(frozen=True)
class MarketView:
    """A trader's memory of one market."""

    prices: dict[str, float]
    surplus: dict[str, float]
    shortfall: dict[str, float]
    day: int

    @classmethod
    def unvisited(cls) -> "MarketView":
        return cls(
            prices={good: GOODS[good].base_price for good in GOOD_NAMES},
            surplus={good: UNKNOWN_SURPLUS for good in GOOD_NAMES},
            shortfall={good: UNKNOWN_SHORTFALL for good in GOOD_NAMES},
            day=-1,
        )


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Policy:
    """A colony's trading stance: the part of the economy its steward owns.

    Every dial is a multiplier on what the colony would otherwise do, so an
    empty policy is the plain economy. Values are clamped on the way in, which
    means an agent driving a steward can ask for anything at all without
    putting the simulation into a state the rest of the code has to defend
    against.
    """

    #: On the price scarcity alone would set. Above 1 the colony is bidding
    #: for imports and charging visitors more; below 1 it is discounting to
    #: shift stock.
    markup: dict[str, float] = field(default_factory=dict)
    #: On the good's own buffer days. Above 1 the colony holds more back and
    #: so has less to sell and more it wants to buy.
    reserve_mult: dict[str, float] = field(default_factory=dict)
    #: On the land's own output. Rebalanced so the colony's total output at
    #: base prices is unchanged: people move between jobs, they do not appear.
    focus: dict[str, float] = field(default_factory=dict)

    def markup_for(self, good: str) -> float:
        return clamp(self.markup.get(good, 1.0), MIN_MARKUP, MAX_MARKUP)

    def reserve_for(self, good: str) -> float:
        return clamp(self.reserve_mult.get(good, 1.0), MIN_RESERVE, MAX_RESERVE)

    def focus_for(self, good: str) -> float:
        return clamp(self.focus.get(good, 1.0), MIN_FOCUS, MAX_FOCUS)

    def set_markup(self, good: str, value: float) -> float:
        self.markup[good] = clamp(value, MIN_MARKUP, MAX_MARKUP)
        return self.markup[good]

    def set_reserve(self, good: str, value: float) -> float:
        self.reserve_mult[good] = clamp(value, MIN_RESERVE, MAX_RESERVE)
        return self.reserve_mult[good]

    def set_focus(self, good: str, value: float) -> float:
        self.focus[good] = clamp(value, MIN_FOCUS, MAX_FOCUS)
        return self.focus[good]

    def rebalance_focus(self, shares: dict[str, float]) -> None:
        """Scale the focus weights so no labour is created by reassigning it.

        `shares` is what each good is worth to the colony at base prices, which
        is the nearest thing the sim has to how many people work on it. Clamp
        and rescale until both hold; a few passes is always enough at these
        bounds, and the last pass favours conservation over the clamp so the
        total can be relied on exactly.
        """
        total = sum(shares.values())
        if total <= 0:
            return
        for _ in range(4):
            self.focus = {
                good: clamp(weight, MIN_FOCUS, MAX_FOCUS)
                for good, weight in self.focus.items()
            }
            spent = sum(shares.get(good, 0.0) * self.focus_for(good) for good in shares)
            if spent <= 0:
                return
            if abs(spent - total) < 1e-9:
                return
            scale = total / spent
            self.focus = {
                good: self.focus_for(good) * scale for good in shares
            }

    def adjustments(self) -> dict[str, dict[str, float]]:
        """Everything this policy actually changes, for display and for logs."""
        return {
            "markup": {
                g: round(self.markup_for(g), 3)
                for g in sorted(self.markup)
                if abs(self.markup_for(g) - 1.0) > 0.01
            },
            "reserve": {
                g: round(self.reserve_for(g), 3)
                for g in sorted(self.reserve_mult)
                if abs(self.reserve_for(g) - 1.0) > 0.01
            },
            "focus": {
                g: round(self.focus_for(g), 3)
                for g in sorted(self.focus)
                if abs(self.focus_for(g) - 1.0) > 0.01
            },
        }

    def is_default(self) -> bool:
        return not any(self.adjustments().values())


@dataclass
class Storage:
    """A storage building: how much of each good is on the shelves."""

    stock: dict[str, float] = field(
        default_factory=lambda: {name: 0.0 for name in GOOD_NAMES}
    )

    def get(self, good: str) -> float:
        return self.stock.get(good, 0.0)

    def add(self, good: str, qty: float) -> None:
        if qty < 0:
            raise ValueError("remove goods with remove()")
        self.stock[good] = self.get(good) + qty

    def remove(self, good: str, qty: float) -> float:
        """Take up to `qty` off the shelves. Returns what was actually taken."""
        taken = min(self.get(good), max(qty, 0.0))
        self.stock[good] = self.get(good) - taken
        return taken

    def total(self) -> float:
        return sum(self.stock.values())


@dataclass
class Colony:
    """A settlement with people, a storage building, and a purse."""

    settlement: Settlement
    #: How many people live here. A live quantity: `people.step` moves it every
    #: day on how well the colony has been eating, and `resize` carries the
    #: change through into what the colony makes and eats. Kept as a float so a
    #: village of twenty can lose a fifth of a person a day and mean it; round
    #: it for display.
    population: float
    production: dict[str, float]
    consumption: dict[str, float]
    storage: Storage = field(default_factory=Storage)
    purse: Purse = field(default_factory=lambda: Purse(SILVER))
    #: The share of its food demand the colony has been meeting lately, smoothed
    #: over about a fortnight. 1.0 is everyone fed.
    nourishment: float = 1.0
    #: Who has arrived and who has gone, since founding. For the viewer, and so
    #: a run can be asked what actually happened to a colony rather than only
    #: where it ended up.
    born: float = 0.0
    starved: float = 0.0
    left: float = 0.0
    #: The stance its steward has taken. Empty means the colony trades on
    #: scarcity alone, exactly as it did before stewards existed.
    policy: Policy = field(default_factory=Policy)
    #: What this colony believes other markets look like, from the last caravan
    #: that came back from each. Deliberately stale: acting on old information
    #: is what produces wasted trips, which is the interesting part.
    known: dict[int, "MarketView"] = field(default_factory=dict)

    @property
    def id(self) -> int:
        return self.settlement.id

    @property
    def name(self) -> str:
        return self.settlement.name

    def reserve(self, good: str) -> float:
        """How much the colony keeps back for itself.

        The good's own buffer, times whatever its steward has decided about
        this good. Raising the reserve is how a colony stops selling something
        and starts wanting it, without anything else in the sim being told.
        """
        return (
            self.consumption.get(good, 0.0)
            * GOODS[good].buffer_days
            * self.policy.reserve_for(good)
        )

    def reserve_days(self, good: str) -> float:
        """The buffer this colony is actually keeping, in days."""
        return GOODS[good].buffer_days * self.policy.reserve_for(good)

    def surplus(self, good: str) -> float:
        """Everything above the reserve, and the only thing that is for sale."""
        return max(0.0, self.storage.get(good) - self.reserve(good))

    def shortfall(self, good: str) -> float:
        """How far below the reserve the colony is, and so what it will buy."""
        return max(0.0, self.reserve(good) - self.storage.get(good))

    def scarcity_price(self, good: str) -> float:
        """Scarcity against the colony's own reserve sets the local price.

        At exactly the reserve a good sells for its base price; below it the
        price climbs, above it the price falls. Two colonies therefore quote
        different prices for the same good, and that gap is what a trader
        earns. As goods move the gap closes, so the economy settles itself.
        """
        reserve = self.reserve(good)
        if reserve <= 0.0:
            # The colony has no use for this good, so it is worth little here.
            return GOODS[good].base_price * MIN_MULT
        ratio = self.storage.get(good) / reserve
        # Shaped so an empty store pays the ceiling, a full reserve pays
        # exactly the base price, and a glut tails off to the floor.
        mult = MAX_MULT / (1.0 + ratio * (MAX_MULT - 1.0))
        return GOODS[good].base_price * max(MIN_MULT, min(MAX_MULT, mult))

    def price(self, good: str) -> float:
        """What this colony actually quotes: scarcity, times its own stance.

        One price serves both sides of the counter, which is what gives a
        steward something real to decide. Raising it makes every other colony
        see a fatter margin for hauling the good here, and makes the colony pay
        more for it when the caravan arrives; cutting it undercuts whoever else
        could supply the same buyer, at less coin per unit.
        """
        return self.scarcity_price(good) * self.policy.markup_for(good)

    def price_ceiling(self, good: str) -> float:
        """The most this good can fetch here, whatever a caravan asks.

        It moves with the colony's own stance, so a steward that has bid its
        prices up is not then capped below what it said it would pay.
        """
        return GOODS[good].base_price * MAX_MULT * self.policy.markup_for(good)

    @property
    def growth(self) -> float:
        """Net people gained since founding: everyone born, less everyone lost.

        Not the same as today's population minus its founding size -- it is,
        but this says so in the terms that produced it, and it is the number a
        colony is actually judged on.
        """
        return self.born - self.starved - self.left

    def resize(self, population: float) -> None:
        """Change how many people live here, and everything that follows.

        Eating is per head, so consumption moves with the population exactly.
        Making things is not: the land the village works does not get any
        bigger when more people are born onto it, so output follows the
        population only as far as `LAND_ELASTICITY` allows. That gap is the
        ceiling a colony grows into -- and the reason a colony that has grown
        past its own fields has to buy food from one that has not.

        Applied as a ratio rather than from a remembered founding size, so it
        composes with `calibrate` and with anything else that has scaled these
        rates, and a run of small daily changes multiplies out to the same
        thing as one large one.
        """
        population = max(MIN_POPULATION, population)
        if self.population <= 0:
            self.population = population
            return
        ratio = population / self.population
        if ratio == 1.0:
            self.population = population
            return
        land = ratio**LAND_ELASTICITY
        for good in self.production:
            self.production[good] *= land
        for good in self.consumption:
            self.consumption[good] *= ratio
        self.population = population

    def output(self, good: str, season: dict[str, float] | None = None) -> float:
        """What the colony makes in a day.

        The land's rate, times where its steward has put the people, times what
        the season allows. `season` is a season's own `growth` table, or None
        for a world with no calendar in it -- which is the control case for
        every claim about what the seasons do.
        """
        return (
            self.production.get(good, 0.0)
            * self.policy.focus_for(good)
            * (season.get(good, 1.0) if season else 1.0)
        )

    def labour_shares(self) -> dict[str, float]:
        """What each good's baseline output is worth at ordinary prices.

        The nearest thing this sim has to how many people work on what, and so
        the weights a focus change has to conserve.
        """
        return {
            good: self.production.get(good, 0.0) * GOODS[good].base_price
            for good in GOOD_NAMES
        }

    def prices(self) -> dict[str, float]:
        return {good: self.price(good) for good in GOOD_NAMES}

    def market_view(self, day: int) -> "MarketView":
        """What a visiting trader sees and takes home.

        Price alone is not enough to trade on: a colony sitting exactly on its
        reserve quotes an ordinary price and will still sell nothing. A trader
        has to remember what was actually for sale.
        """
        return MarketView(
            prices=self.prices(),
            surplus={good: self.surplus(good) for good in GOOD_NAMES},
            shortfall={good: self.shortfall(good) for good in GOOD_NAMES},
            day=day,
        )

    def live_day(
        self, season: dict[str, float] | None = None
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Produce and consume one day. Returns what was made and what was used.

        Consumption is capped at what is on the shelves, so a colony that runs
        out simply goes without rather than driving stock negative. Production
        is not: the season decides it, and a winter that makes nothing is the
        whole point of having one.
        """
        made: dict[str, float] = {}
        used: dict[str, float] = {}
        for good in self.production:
            rate = self.output(good, season)
            if rate:
                self.storage.add(good, rate)
                made[good] = rate
        for good, rate in self.consumption.items():
            if rate:
                used[good] = self.storage.remove(good, rate)
        return made, used
