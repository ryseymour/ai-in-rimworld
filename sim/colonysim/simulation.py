"""The day loop that ties world, roads, storage and traders together."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .crafting import WEAR_PER_CAPITA, armed_strength, work_day
from .goods import GOOD_NAMES, GOODS, RAW_GOOD_NAMES
from .hunting import ARROWS_PER_CAPITA, hunt
from .money import SILVER, Purse
from .roads import RoadNetwork, apply_traffic, generate_roads, route_between
from .steward import Link, NetworkView, Steward, route_tier
from .storage import Colony, MarketView, Storage
from .trade import (
    HOME,
    MIN_TRIP_COIN,
    MIN_TRIP_WORTH,
    OUTBOUND,
    RETURNING,
    Caravan,
    cautious_capacity,
    do_business,
    expected_profit,
    expected_relief,
    plan_cargo,
    travel_days,
    trip_float,
    unload,
)
from .wildlife import Wilds, escort_cost, expected_loss, per_day_hazard, populate, raid
from .world import World, generate_world

#: Per head, per day. The raw goods are eaten, burnt and worn out; the crafted
#: ones break (`crafting.WEAR_PER_CAPITA`) or are shot away hunting
#: (`hunting.ARROWS_PER_CAPITA`). All of it is the same number to the rest of
#: the sim: what a colony uses is what sets its reserve, and so its prices.
CONSUMPTION_PER_CAPITA = {
    "food": 0.55,
    "wood": 0.18,
    "stone": 0.06,
    "cloth": 0.03,
    "tools": 0.012,
    "arrows": ARROWS_PER_CAPITA,
    **WEAR_PER_CAPITA,
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

#: How dearly a trader treats a dangerous leg when choosing its way there: a
#: route that is certain to be attacked is worth going this much further round
#: to avoid. The detour is paid in travel cost, which is the same currency the
#: road graph is already searched in.
DANGER_DETOUR = 0.8


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
    # Only the raw goods: everything else on the shelves was made by somebody.
    production = {
        good: consumption[good]
        * sum(fraction * AFFINITY[good][kind] for kind, fraction in mix.items())
        for good in RAW_GOOD_NAMES
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
    # imbalance that appears later was produced by the simulation itself. That
    # includes the crafted goods: a village that has been there a while has its
    # axes and its quiver, and the workshop's job is to keep up with what wears
    # out rather than to arm the place from nothing.
    for good in GOOD_NAMES:
        colony.storage.add(good, colony.reserve(good))
    return colony


def calibrate(colonies: list[Colony], surplus: float = SURPLUS_FACTOR) -> None:
    """Scale world production so it covers world consumption.

    Terrain decides who makes what; this only decides how much the world makes
    in total. Each colony keeps its own share, so specialisation -- and the
    imbalance between colonies -- survives untouched. Crafted goods are not in
    here: what a workshop makes is decided day by day, out of materials this
    has already scaled.
    """
    for good in RAW_GOOD_NAMES:
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
    #: One per colony, in colony order, or empty for a world where nobody is
    #: minding the shop. Empty is the control case for every claim about what
    #: stewards do to an economy.
    stewards: list[Steward] = field(default_factory=list)
    caravans: list[Caravan] = field(default_factory=list)
    day: int = 0
    produced: dict[str, float] = field(default_factory=dict)
    consumed: dict[str, float] = field(default_factory=dict)
    journeys: int = 0
    #: Turn trade off to see what the same world does without it. The control
    #: case for every claim that trade is doing something.
    trade_enabled: bool = True
    #: The animals. `None` is a tame world, and the control case for every
    #: claim about what the wildlife does.
    wilds: Wilds | None = None
    #: Goods eaten or trampled by animals. Nothing else in the sim destroys
    #: goods, so conservation is checked against this.
    lost: dict[str, float] = field(default_factory=dict)
    #: Coin paid to guards. It leaves the trading economy, so it comes out of
    #: the conserved total the same way.
    escort_wages: float = 0.0
    #: Every meeting on the road, including the ones that came to nothing.
    meetings: int = 0
    #: Meetings where the animals got at the cargo.
    raids: int = 0
    #: What the workshops made and what the hunters brought home. Both are part
    #: of `produced` -- these are kept apart so the thing can be reported on.
    crafted: dict[str, float] = field(default_factory=dict)
    hunted: dict[str, float] = field(default_factory=dict)
    journeys_turned_back: int = 0
    log: list[str] = field(default_factory=list)
    #: Encounters are the one roll of the dice in the sim. Seeded from the
    #: world, so a seed still replays exactly.
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    _next_caravan_id: int = 0
    #: Route hazards, worked out once a day. A road's danger moves only as its
    #: tier and the dens near it move, both of which change by the day, while
    #: every colony asks about every route it could take -- so without this the
    #: same tiles get walked hundreds of times before breakfast.
    _hazard_today: dict[tuple[int, int], float] = field(default_factory=dict)
    #: Ways there, worked out once a day as well. Stewards and traders ask the
    #: same question of the same graph on the same day, so they share a cache
    #: and the answers cannot disagree.
    _routes_today: dict[tuple[int, int], tuple] = field(default_factory=dict)

    # ---------------------------------------------------------------- totals
    def goods_in_world(self) -> dict[str, float]:
        """Everything on every shelf plus everything on the road.

        Trade must never change this. Only production, consumption, and what
        the animals take (`lost`) may.
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

    def goods_lost(self) -> float:
        return sum(self.lost.values())

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
        self._hazard_today.clear()
        self._routes_today.clear()

        for colony in self.colonies:
            made, used = colony.live_day()
            self._made(made)
            self._used(used)
            # The arrows the day's consumption just took off the shelves are the
            # hunt: a colony with a full quiver comes home with meat and hides,
            # one with none comes home with nothing.
            self._hunt(colony, used.get("arrows", 0.0))
            # Then the benches, on whatever the colony can spare.
            self._craft(colony)

        if self.wilds is not None:
            self.wilds.settle_day(self.network)

        # Stewards decide before anyone is dispatched, so a caravan leaving
        # today leaves under today's prices rather than yesterday's.
        self._review_markets()

        if self.trade_enabled:
            self._advance_caravans()
            self._dispatch()

    # ------------------------------------------------- production and the wild
    def _made(self, made: dict[str, float]) -> None:
        for good, qty in made.items():
            self.produced[good] = self.produced.get(good, 0.0) + qty

    def _used(self, used: dict[str, float]) -> None:
        for good, qty in used.items():
            self.consumed[good] = self.consumed.get(good, 0.0) + qty

    def _craft(self, colony: Colony) -> None:
        """A day at the colony's benches.

        Crafting is production and consumption like any other: the materials go
        into `consumed` and what came off the bench into `produced`, so the
        conservation check in `goods_in_world` still accounts for every unit.
        """
        made, used = work_day(colony)
        self._made(made)
        self._used(used)
        for good, qty in made.items():
            self.crafted[good] = self.crafted.get(good, 0.0) + qty

    def _hunt(self, colony: Colony, arrows: float) -> None:
        """What the hunting party brought back for the arrows it spent."""
        if arrows <= 0.0:
            return
        bag = hunt(colony, arrows)
        self._made(bag)
        for good, qty in bag.items():
            self.hunted[good] = self.hunted.get(good, 0.0) + qty

    # ------------------------------------------------------------- stewards
    def _route(self, home: int, other: int) -> tuple:
        """Today's best way from one colony to another, danger priced in."""
        key = (home, other)
        legs = self._routes_today.get(key)
        if legs is None:
            legs = route_between(
                self.network, home, other, surcharge=self._danger_surcharge
            )
            self._routes_today[key] = legs
        return legs

    def network_view(self, colony_id: int) -> NetworkView:
        """The trade network as one colony's steward can see it.

        The roads are today's -- their length, their danger, how worn they are.
        The markets are not: each one is whatever the last caravan home from
        there brought back, which is where a steward's mistakes come from.
        """
        colony = self.colonies[colony_id]
        links: dict[int, Link] = {}
        for other in range(len(self.colonies)):
            if other == colony_id:
                continue
            legs = self._route(colony_id, other)
            if not legs:
                continue
            links[other] = Link(
                colony=other,
                name=self.colonies[other].name,
                days=travel_days(self.world.terrain, self.network, legs),
                hazard=self._leg_hazard(legs),
                tier=route_tier(self.network, legs),
                legs=legs,
                market=colony.known.get(other) or MarketView.unvisited(),
            )
        return NetworkView(
            day=self.day,
            home=colony_id,
            links=links,
            caravans=tuple(c for c in self.caravans if c.home == colony_id),
        )

    def _review_markets(self) -> None:
        for steward in self.stewards:
            steward.review(self.network_view(steward.colony.id))

    # ------------------------------------------------------------- wildlife
    def _route_hazard(self, route) -> float:
        """Today's danger on one carved road, worked out at most once."""
        if self.wilds is None:
            return 0.0
        hazard = self._hazard_today.get(route.key)
        if hazard is None:
            hazard = self.wilds.route_hazard(self.network, route)
            self._hazard_today[route.key] = hazard
        return hazard

    def _leg_hazard(self, legs: tuple) -> float:
        """Chance of meeting something over one leg of a journey."""
        safe = 1.0
        for leg in legs:
            safe *= 1.0 - self._route_hazard(leg)
        return 1.0 - safe

    def _danger_surcharge(self, route) -> float:
        """What a leg's danger is worth in extra travel cost when choosing a
        way there. This is the whole of routing around the animals: a wolf
        valley simply costs more to walk through, so Dijkstra goes round."""
        return route.cost * DANGER_DETOUR * self._route_hazard(route)

    def _walk_a_day(self, caravan: Caravan) -> None:
        """Roll for one day on the road, and deal with what turns up."""
        if self.wilds is None or caravan.hazard <= 0.0:
            return
        days = max(1.0, travel_days(self.world.terrain, self.network, caravan.legs))
        if self.rng.random() >= per_day_hazard(caravan.hazard, days):
            return

        path = tuple(tile for leg in caravan.legs for tile in leg.path)
        den = self.wilds.pick_den(self.rng, self.network, path)
        if den is None:
            return

        encounter = raid(
            self.rng, den, caravan.cargo, caravan.escorted, self.day, caravan.arms
        )
        caravan.encounters.append(encounter)
        self.meetings += 1
        caravan.ledger.append(encounter.describe())
        for good, qty in encounter.losses.items():
            self.lost[good] = self.lost.get(good, 0.0) + qty
        if encounter.outcome != "drove off":
            self.raids += 1
        if encounter.outcome == "routed" and caravan.state == OUTBOUND:
            # It never gets where it was going. Whatever is left goes home,
            # from wherever on the road it turned around.
            caravan.state = RETURNING
            caravan.days_left = caravan.leg_days = travel_days(
                self.world.terrain, self.network, caravan.legs
            )
            self.journeys_turned_back += 1

    def _advance_caravans(self) -> None:
        for caravan in list(self.caravans):
            if caravan.state == HOME:
                continue
            self._walk_a_day(caravan)
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
                legs = self._route(colony.id, other)
                if not legs:
                    continue
                known = colony.known.get(other) or MarketView.unvisited()
                hazard = self._leg_hazard(legs)
                # Less on the road where there is more to lose it to.
                cargo = plan_cargo(colony, known, cautious_capacity(hazard))
                worth = expected_profit(colony, known, cargo)
                if colony.purse.amount >= MIN_TRIP_COIN:
                    worth += expected_relief(colony, known)
                if not cargo and colony.purse.amount < MIN_TRIP_COIN:
                    continue
                # Round trip plus a day trading, so a short hop cannot win on
                # the divisor alone while delivering nothing worth having.
                days = 2 * travel_days(self.world.terrain, self.network, legs) + 1
                # Both legs are exposed. What goes out is the cargo; what
                # comes back is whatever the coin turned into, so the float
                # counts too -- which is why a colony that sets out to buy
                # rather than to sell is still taking a risk worth pricing.
                at_risk = (
                    expected_profit(colony, known, cargo)
                    + sum(qty * colony.price(good) for good, qty in cargo.items())
                    + trip_float(colony)
                )
                escorted, risk = self._escort_decision(
                    colony, hazard, at_risk, days, armed_strength(colony)
                )
                score = (worth - risk) / days
                if best is None or score > best[0]:
                    best = (score, worth - risk, other, legs, cargo, hazard, escorted)

            if best is None or best[1] < MIN_TRIP_WORTH:
                continue

            _, _, other, legs, cargo, hazard, escorted = best
            arms = armed_strength(colony)
            caravan = Caravan(
                id=self._next_caravan_id,
                home=colony.id,
                destination=other,
                legs=legs,
                days_left=travel_days(self.world.terrain, self.network, legs),
                leg_days=travel_days(self.world.terrain, self.network, legs),
                dispatched_day=self.day,
                hazard=hazard,
                escorted=escorted,
                arms=arms,
            )
            self._next_caravan_id += 1
            for good, qty in cargo.items():
                caravan.cargo[good] = colony.storage.remove(good, qty)
            if escorted:
                days = 2 * travel_days(self.world.terrain, self.network, legs) + 1
                wage = colony.purse.withdraw(escort_cost(days, arms))
                self.escort_wages += wage
                caravan.ledger.append(f"hired guards for {wage:.0f} coin")
            colony.purse.transfer_to(caravan.purse, trip_float(colony))
            self.caravans.append(caravan)

    def _escort_decision(
        self,
        colony: Colony,
        hazard: float,
        at_risk: float,
        days: float,
        arms: float = 0.0,
    ) -> tuple[bool, float]:
        """Guards, or no guards, and what the risk costs either way.

        A colony with coin buys its way out of the problem; a colony without
        one takes its chances. The comparison is the plain one -- what the
        animals are expected to take, against what the guards want -- so the
        wolves are a reason to earn coin rather than a flat tax on trading.

        Weapons come in on both sides of that sum: an armed party loses less
        whether or not it hires anyone, and the guards it does hire come
        cheaper, so a colony that crafts spears trades more freely than one
        that does not.
        """
        bare = expected_loss(hazard, at_risk, arms=arms)
        if self.wilds is None or hazard <= 0.0:
            return False, bare
        wage = escort_cost(days, arms)
        guarded = expected_loss(hazard, at_risk, escorted=True, arms=arms) + wage
        if guarded < bare and colony.purse.amount >= wage + MIN_TRIP_COIN:
            return True, guarded
        return False, bare

    def run(self, days: int) -> None:
        for _ in range(days):
            self.step_day()


def build_simulation(
    seed: int = 1,
    settlements: int = 6,
    width: int = 90,
    height: int = 45,
    wildlife: bool = True,
    stewards: bool = True,
) -> Simulation:
    """A world, its roads, its colonies, and whoever is running them.

    `stewards=False` leaves every colony trading on bare scarcity, which is the
    world this sim had before anyone was in charge of one -- and so the control
    case to compare a steward-run economy against.
    """
    world = generate_world(width, height, settlements, seed)
    network = generate_roads(world)
    rng = random.Random(seed ^ 0xC0FFEE)
    colonies = [
        build_colony(world, s, population=rng.randint(14, 30)) for s in world.settlements
    ]
    calibrate(colonies)
    return Simulation(
        world=world,
        network=network,
        colonies=colonies,
        stewards=[Steward(colony) for colony in colonies] if stewards else [],
        wilds=populate(world, seed) if wildlife else None,
        rng=random.Random(seed ^ 0xD00D),
    )
