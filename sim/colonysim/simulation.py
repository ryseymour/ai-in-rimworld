"""The day loop that ties world, roads, storage and traders together."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .goods import GOOD_NAMES, GOODS
from .money import SILVER, Purse
from .roads import RoadNetwork, apply_traffic, generate_roads, route_between
from .storage import Colony, MarketView, Storage
from .trade import (
    HOME,
    MIN_TRIP_COIN,
    MIN_TRIP_WORTH,
    OUTBOUND,
    RETURNING,
    Caravan,
    do_business,
    expected_profit,
    expected_relief,
    plan_cargo,
    travel_days,
    trip_float,
    unload,
)
from .world import World, generate_world

#: Per head, per day.
CONSUMPTION_PER_CAPITA = {
    "food": 0.55,
    "wood": 0.18,
    "stone": 0.06,
    "cloth": 0.03,
    "tools": 0.012,
}
#: How good each terrain is at each good, relative to average land. A village
#: ringed by forest makes three times the wood and a quarter of the stone.
AFFINITY = {
    "food": {"plains": 1.9, "water": 1.3, "forest": 0.7, "rough": 0.25},
    "wood": {"forest": 3.0, "rough": 0.5, "plains": 0.45, "water": 0.1},
    "stone": {"rough": 3.4, "forest": 0.7, "plains": 0.6, "water": 0.15},
    "cloth": {"plains": 1.8, "forest": 0.8, "water": 0.6, "rough": 0.5},
    "tools": {"rough": 2.6, "forest": 0.9, "plains": 0.8, "water": 0.3},
}
#: Radius of the land a village works.
CATCHMENT = 7
#: The world is calibrated to produce this much more than it eats. Trade is a
#: distribution problem; a world in deficit would starve whatever traders did,
#: and would tell us nothing about whether the trade code works.
SURPLUS_FACTOR = 1.12
STARTING_SILVER = 900.0


def terrain_mix(world: World, x: int, y: int, radius: int = CATCHMENT) -> dict[str, float]:
    """The fractions of each terrain within a village's reach."""
    counts: dict[str, int] = {}
    total = 0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            tx, ty = x + dx, y + dy
            if dx * dx + dy * dy > radius * radius or not world.terrain.in_bounds(tx, ty):
                continue
            kind = world.terrain.kind(tx, ty)
            counts[kind] = counts.get(kind, 0) + 1
            total += 1
    return {kind: n / total for kind, n in counts.items()} if total else {}


def build_colony(world: World, settlement, population: int) -> Colony:
    """A village makes what the land around it allows.

    Production is its own consumption, scaled by how good the surrounding land
    is at each good. That is what creates the imbalance trade exists to fix: a
    village ringed by forest has wood to spare and no stone of its own.
    """
    mix = terrain_mix(world, settlement.x, settlement.y)
    consumption = {
        good: rate * population for good, rate in CONSUMPTION_PER_CAPITA.items()
    }
    production = {
        good: consumption[good]
        * sum(fraction * AFFINITY[good][kind] for kind, fraction in mix.items())
        for good in GOOD_NAMES
    }

    colony = Colony(
        settlement=settlement,
        population=population,
        production=production,
        consumption=consumption,
        storage=Storage(),
        purse=Purse(SILVER, STARTING_SILVER),
    )
    # Everyone starts on their reserve, so day one is balanced and any
    # imbalance that appears later was produced by the simulation itself.
    for good in GOOD_NAMES:
        colony.storage.add(good, colony.reserve(good))
    return colony


def calibrate(colonies: list[Colony], surplus: float = SURPLUS_FACTOR) -> None:
    """Scale world production so it covers world consumption.

    Terrain decides who makes what; this only decides how much the world makes
    in total. Each colony keeps its own share, so specialisation -- and the
    imbalance between colonies -- survives untouched.
    """
    for good in GOOD_NAMES:
        made = sum(c.production[good] for c in colonies)
        eaten = sum(c.consumption[good] for c in colonies)
        if made <= 0 or eaten <= 0:
            continue
        scale = (eaten * surplus) / made
        for colony in colonies:
            colony.production[good] *= scale


@dataclass
class Simulation:
    world: World
    network: RoadNetwork
    colonies: list[Colony]
    caravans: list[Caravan] = field(default_factory=list)
    day: int = 0
    produced: dict[str, float] = field(default_factory=dict)
    consumed: dict[str, float] = field(default_factory=dict)
    journeys: int = 0
    #: Turn trade off to see what the same world does without it. The control
    #: case for every claim that trade is doing something.
    trade_enabled: bool = True
    log: list[str] = field(default_factory=list)
    _next_caravan_id: int = 0

    # ---------------------------------------------------------------- totals
    def goods_in_world(self) -> dict[str, float]:
        """Everything on every shelf plus everything on the road.

        Trade must never change this. Only production and consumption may.
        """
        totals = {good: 0.0 for good in GOOD_NAMES}
        for colony in self.colonies:
            for good in GOOD_NAMES:
                totals[good] += colony.storage.get(good)
        for caravan in self.caravans:
            for good, qty in caravan.cargo.items():
                totals[good] += qty
        return totals

    def coin_in_world(self) -> float:
        return sum(c.purse.amount for c in self.colonies) + sum(
            c.purse.amount for c in self.caravans
        )

    def price_spread(self, good: str) -> float:
        """Gap between the dearest and the cheapest colony.

        Everyone starts on their reserve, so this begins at zero and opens up
        as colonies drift apart. The question is never whether it grows, but
        whether it grows less than it would with no traders on the roads.
        """
        prices = [colony.price(good) for colony in self.colonies]
        return max(prices) - min(prices)

    def days_of_stock(self, good: str) -> list[float]:
        """How long each colony could go on what it has. The number that says
        whether trade is actually keeping anyone alive."""
        out = []
        for colony in self.colonies:
            rate = colony.consumption.get(good, 0.0)
            out.append(colony.storage.get(good) / rate if rate else float("inf"))
        return out

    def hungry_colonies(self, good: str = "food") -> list[str]:
        """Colonies with less than a day of a good left."""
        return [
            c.name
            for c, days in zip(self.colonies, self.days_of_stock(good))
            if days < 1.0
        ]

    # ------------------------------------------------------------------ loop
    def step_day(self) -> None:
        self.day += 1

        for colony in self.colonies:
            made, used = colony.live_day()
            for good, qty in made.items():
                self.produced[good] = self.produced.get(good, 0.0) + qty
            for good, qty in used.items():
                self.consumed[good] = self.consumed.get(good, 0.0) + qty

        if self.trade_enabled:
            self._advance_caravans()
            self._dispatch()

    def _advance_caravans(self) -> None:
        for caravan in list(self.caravans):
            if caravan.state == HOME:
                continue
            caravan.days_left -= 1
            if caravan.days_left > 0:
                continue

            for leg in caravan.legs:
                apply_traffic(self.network, leg)
            if caravan.state == OUTBOUND:
                host = self.colonies[caravan.destination]
                do_business(caravan, host, self.colonies[caravan.home], self.day)
                caravan.state = RETURNING
                caravan.days_left = caravan.leg_days = travel_days(
                    self.world.terrain, self.network, caravan.legs
                )
            elif caravan.state == RETURNING:
                unload(caravan, self.colonies[caravan.home])
                self.journeys += 1
                self.log.append(
                    f"day {self.day}: caravan {caravan.id} home to "
                    f"{self.colonies[caravan.home].name} -- "
                    + "; ".join(caravan.ledger)
                )

        self.caravans = [c for c in self.caravans if c.state != HOME]

    def _dispatch(self) -> None:
        """Each colony runs at most one caravan at a time. It picks wherever
        its surplus is worth most per day on the road, using the prices it saw
        on its last visit -- which may well be out of date by now. Anywhere on
        the road network is reachable, not just the next village along, so a
        colony at the end of a chain can still be supplied."""
        busy = {c.home for c in self.caravans}
        for colony in self.colonies:
            if colony.id in busy:
                continue

            best = None
            for other in range(len(self.colonies)):
                if other == colony.id:
                    continue
                legs = route_between(self.network, colony.id, other)
                if not legs:
                    continue
                known = colony.known.get(other) or MarketView.unvisited()
                cargo = plan_cargo(colony, known)
                worth = expected_profit(colony, known, cargo)
                if colony.purse.amount >= MIN_TRIP_COIN:
                    worth += expected_relief(colony, known)
                if not cargo and colony.purse.amount < MIN_TRIP_COIN:
                    continue
                # Round trip plus a day trading, so a short hop cannot win on
                # the divisor alone while delivering nothing worth having.
                days = 2 * travel_days(self.world.terrain, self.network, legs) + 1
                score = worth / days
                if best is None or score > best[0]:
                    best = (score, worth, other, legs, cargo)

            if best is None or best[1] < MIN_TRIP_WORTH:
                continue

            _, _, other, legs, cargo = best
            caravan = Caravan(
                id=self._next_caravan_id,
                home=colony.id,
                destination=other,
                legs=legs,
                days_left=travel_days(self.world.terrain, self.network, legs),
                leg_days=travel_days(self.world.terrain, self.network, legs),
                dispatched_day=self.day,
            )
            self._next_caravan_id += 1
            for good, qty in cargo.items():
                caravan.cargo[good] = colony.storage.remove(good, qty)
            colony.purse.transfer_to(caravan.purse, trip_float(colony))
            self.caravans.append(caravan)

    def run(self, days: int) -> None:
        for _ in range(days):
            self.step_day()


def build_simulation(
    seed: int = 1, settlements: int = 6, width: int = 90, height: int = 45
) -> Simulation:
    world = generate_world(width, height, settlements, seed)
    network = generate_roads(world)
    rng = random.Random(seed ^ 0xC0FFEE)
    colonies = [
        build_colony(world, s, population=rng.randint(14, 30)) for s in world.settlements
    ]
    calibrate(colonies)
    return Simulation(world=world, network=network, colonies=colonies)
