"""The storage building, and the colony that owns it.

Storage is the whole trade interface. What a colony will sell is whatever sits
above its reserve; what it will buy is whatever sits below. Prices follow from
the same number. Nothing scripts the economy -- it falls out of what each
colony actually produces and eats.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .goods import GOOD_NAMES, GOODS
from .money import SILVER, Purse
from .world import Settlement

#: Price multiplier bounds. A glut must not drive a price to nothing, and a
#: famine must not make one good worth more than a caravan.
MIN_MULT = 0.35
MAX_MULT = 3.0


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
    population: int
    production: dict[str, float]
    consumption: dict[str, float]
    storage: Storage = field(default_factory=Storage)
    purse: Purse = field(default_factory=lambda: Purse(SILVER))
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
        """How much the colony keeps back for itself."""
        return self.consumption.get(good, 0.0) * GOODS[good].buffer_days

    def surplus(self, good: str) -> float:
        """Everything above the reserve, and the only thing that is for sale."""
        return max(0.0, self.storage.get(good) - self.reserve(good))

    def shortfall(self, good: str) -> float:
        """How far below the reserve the colony is, and so what it will buy."""
        return max(0.0, self.reserve(good) - self.storage.get(good))

    def price(self, good: str) -> float:
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

    def live_day(self) -> tuple[dict[str, float], dict[str, float]]:
        """Produce and consume one day. Returns what was made and what was used.

        Consumption is capped at what is on the shelves, so a colony that runs
        out simply goes without rather than driving stock negative.
        """
        made: dict[str, float] = {}
        used: dict[str, float] = {}
        for good, rate in self.production.items():
            if rate:
                self.storage.add(good, rate)
                made[good] = rate
        for good, rate in self.consumption.items():
            if rate:
                used[good] = self.storage.remove(good, rate)
        return made, used
