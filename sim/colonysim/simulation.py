"""The day loop that ties world, roads, storage and traders together."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import people
from .goods import GOOD_NAMES, GOODS
from .money import SILVER, Purse
from .roads import (
    RoadNetwork,
    apply_traffic,
    generate_roads,
    journey_grade,
    route_between,
    route_grade,
)
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
from .weather import CLEAR, FORECAST_DAYS, Climate, Weather
from .wildlife import Wilds, escort_cost, expected_loss, per_day_hazard, populate, raid
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

#: How dearly a trader treats a dangerous leg when choosing its way there: a
#: route that is certain to be attacked is worth going this much further round
#: to avoid. The detour is paid in travel cost, which is the same currency the
#: road graph is already searched in.
DANGER_DETOUR = 0.8

#: Most "waited out the snow" lines one caravan's ledger keeps. A journey that
#: sat out four storms has said what it has to say; `days_waited` carries the
#: exact count.
WAIT_NOTES = 3


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


def build_colony(world: World, settlement, population: float) -> Colony:
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
class SeasonTally:
    """What one season of the year did, summed over every year of a run.

    The shape of a year, in the four numbers that show it: what the land gave,
    what it cost to keep the roads working, and whether anyone went hungry.
    """

    days: int = 0
    journeys: int = 0
    #: Days this season on which some road somewhere was shut.
    shut_days: int = 0
    #: Caravan-days lost to sitting out weather.
    waited: float = 0.0
    produced: dict[str, float] = field(default_factory=dict)
    #: Running sum of every colony's price for each good, so the demo can show
    #: a mean price per season without keeping a day-by-day history.
    price_sum: dict[str, float] = field(default_factory=dict)
    price_days: int = 0
    hungry_days: int = 0

    def mean_price(self, good: str) -> float:
        if not self.price_days:
            return 0.0
        return self.price_sum.get(good, 0.0) / self.price_days


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
    #: The year: the calendar, and the sky over it. `None` is a world of
    #: endless temperate weather, and the control case for every claim about
    #: what the seasons do.
    climate: Climate | None = None
    #: Caravan-days spent sitting still because a road was shut. Weather costs
    #: the economy time, never goods -- conservation is untouched by it, which
    #: is what makes that check still exact with seasons in the world.
    days_waited: float = 0.0
    #: Days on which at least one carved road was closed somewhere.
    days_roads_shut: int = 0
    #: Days each colony has spent with less than a day of food left, over the
    #: whole run. With a calendar in the world, asking who is hungry on the
    #: last day asks about one week of one season -- nobody is hungry in
    #: autumn. Whether a colony ever went hungry is the question that survives
    #: having a year.
    hungry_days: dict[str, int] = field(default_factory=dict)
    #: What each season of the year did, accumulated over however many years
    #: the run covers. This is the shape of the year, and what the demo prints.
    tallies: dict[str, "SeasonTally"] = field(default_factory=dict)
    #: Goods eaten or trampled by animals. Nothing else in the sim destroys
    #: goods, so conservation is checked against this.
    lost: dict[str, float] = field(default_factory=dict)
    #: Coin paid to guards. It leaves the trading economy, so it comes out of
    #: the conserved total the same way.
    escort_wages: float = 0.0
    #: Whether people follow food. `False` freezes every colony at its founding
    #: size, which is the world this sim had before population was a live
    #: quantity, and so the control case for every claim about what it does.
    population_moves: bool = True
    #: People, since day one. Births, then the two ways a colony loses someone:
    #: hunger, and walking out while there is still something to eat.
    born: float = 0.0
    starved: float = 0.0
    left: float = 0.0
    #: Every meeting on the road, including the ones that came to nothing.
    meetings: int = 0
    #: Meetings where the animals got at the cargo.
    raids: int = 0
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
    #: The same question with the weather ignored: the road that exists even on
    #: a day it cannot be walked. A steward still needs to see a snowed-in
    #: neighbour, or it could not plan for the thaw.
    _open_today: dict[tuple[int, int], tuple] = field(default_factory=dict)

    # -------------------------------------------------------------- the year
    @property
    def date(self):
        """Today on the calendar. Every world has one, weather or not."""
        from .weather import date_of

        return self.climate.date(self.day) if self.climate else date_of(self.day)

    @property
    def weather(self) -> Weather:
        """Today's sky, or fair weather in a world with no climate."""
        return self.climate.on(self.day) if self.climate else CLEAR

    @property
    def season(self):
        return self.date.season

    def growth(self) -> dict[str, float] | None:
        """Today's multiplier on the land, or None where there is no calendar."""
        return self.climate.growth(self.day) if self.climate else None

    def route_shut(self, route) -> bool:
        """Whether today's weather has this carved road closed.

        A route is judged on its mean tier, so it is the road as a whole that
        shuts, and a trunk worn up to a dirt road rides out the snow that
        closes the foot path beside it.
        """
        if self.climate is None:
            return False
        return self.weather.shuts(route_grade(self.network, route))

    def shut_routes(self) -> list:
        return [r for r in self.network.routes.values() if self.route_shut(r)]

    def forecast_days(self, legs: tuple) -> float:
        """How long a journey will really take, setting out today.

        The bare road distance, walked through the week the forecast says is
        coming. This is what a trader decides on; `travel_days` alone is what
        it then counts down.
        """
        plain = travel_days(self.world.terrain, self.network, legs)
        if self.climate is None or not legs:
            return plain
        return self.climate.journey_days(
            self.day, plain, journey_grade(self.network, legs)
        )

    def _tally(self) -> "SeasonTally":
        return self.tallies.setdefault(self.season.name, SeasonTally())

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

    def population(self) -> float:
        """Everyone alive in the world."""
        return sum(colony.population for colony in self.colonies)

    def shrinking_colonies(self) -> list[str]:
        """Colonies that have lost people on the balance -- at least one of
        them, so a village down a fraction of a person does not count.

        The economy's own scoreboard: a colony only gets here by having been
        unable to feed itself for long enough that people left or died, which
        trade and a steward both exist to prevent.
        """
        return [colony.name for colony in self.colonies if colony.growth <= -1.0]

    def hungry_colonies(self, good: str = "food") -> list[str]:
        """Colonies with less than a day of a good left, today."""
        return [
            c.name
            for c, days in zip(self.colonies, self.days_of_stock(good))
            if days < 1.0
        ]

    def ever_hungry(self) -> list[str]:
        """Colonies that ran out of food at any point in the run.

        The claim about trade has to be made on the whole run rather than on
        the last day of it: with seasons, the last day is somewhere in a
        particular season, and nobody is hungry in autumn.
        """
        return sorted(self.hungry_days)

    # ------------------------------------------------------------------ loop
    def step_day(self) -> None:
        self.day += 1
        self._hazard_today.clear()
        self._routes_today.clear()
        self._open_today.clear()

        tally = self._tally()
        tally.days += 1
        growth = self.growth()

        for colony in self.colonies:
            wanted = colony.consumption.get("food", 0.0)
            made, used = colony.live_day(growth)
            for good, qty in made.items():
                self.produced[good] = self.produced.get(good, 0.0) + qty
                tally.produced[good] = tally.produced.get(good, 0.0) + qty
            for good, qty in used.items():
                self.consumed[good] = self.consumed.get(good, 0.0) + qty
            # How much of what the colony wanted to eat it actually got, read
            # before anyone is born or buried, since both change what it wants.
            ration = used.get("food", 0.0) / wanted if wanted > 0 else 1.0
            self._live_people(colony, ration)

        if self.shut_routes():
            self.days_roads_shut += 1
            tally.shut_days += 1

        if self.wilds is not None:
            self.wilds.settle_day(self.network)

        # Stewards decide before anyone is dispatched, so a caravan leaving
        # today leaves under today's prices rather than yesterday's.
        self._review_markets()

        if self.trade_enabled:
            self._advance_caravans()
            self._dispatch()

        self._record_prices(tally)

    def _record_prices(self, tally: SeasonTally) -> None:
        """What the world was asking today, for the season's average."""
        for good in GOOD_NAMES:
            tally.price_sum[good] = tally.price_sum.get(good, 0.0) + sum(
                colony.price(good) for colony in self.colonies
            ) / len(self.colonies)
        tally.price_days += 1
        hungry = self.hungry_colonies()
        tally.hungry_days += len(hungry)
        for name in hungry:
            self.hungry_days[name] = self.hungry_days.get(name, 0) + 1

    # --------------------------------------------------------------- people
    def _live_people(self, colony: Colony, ration: float) -> None:
        """Births, hunger and departures for one colony, for one day."""
        if not self.population_moves:
            return
        change = people.step(colony, ration)
        self.born += change.born
        self.starved += change.starved
        self.left += change.left

    # ------------------------------------------------------------- stewards
    def _route(self, home: int, other: int) -> tuple:
        """The way from one colony to another as the map has it: danger priced
        in, weather ignored. The road that exists, whether or not it can be
        walked today."""
        key = (home, other)
        legs = self._routes_today.get(key)
        if legs is None:
            legs = route_between(
                self.network, home, other, surcharge=self._danger_surcharge
            )
            self._routes_today[key] = legs
        return legs

    def _open_route(self, home: int, other: int) -> tuple:
        """The way there that can actually be walked today.

        The shut legs are taken out of the graph rather than made expensive, so
        the search finds whatever open chain is left: a snowed-in pass pushes
        the caravan onto the long valley road instead of stopping it. Empty
        when the weather has cut the two apart altogether.
        """
        if self.climate is None:
            return self._route(home, other)
        key = (home, other)
        legs = self._open_today.get(key)
        if legs is None:
            legs = route_between(
                self.network,
                home,
                other,
                surcharge=self._danger_surcharge,
                blocked=self.route_shut,
            )
            self._open_today[key] = legs
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
            legs = self._open_route(colony_id, other)
            walkable = bool(legs)
            if not walkable:
                # Shut today, but the road is still there: show it, so the
                # steward can price for the thaw rather than forgetting the
                # village exists.
                legs = self._route(colony_id, other)
            if not legs:
                continue
            grade = journey_grade(self.network, legs)
            links[other] = Link(
                colony=other,
                name=self.colonies[other].name,
                days=travel_days(self.world.terrain, self.network, legs),
                hazard=self._leg_hazard(legs),
                tier=route_tier(self.network, legs),
                legs=legs,
                market=colony.known.get(other) or MarketView.unvisited(),
                open=walkable,
                weather_days=self.forecast_days(legs) if walkable else 0.0,
                outlook=(
                    self.climate.outlook(self.day, grade) if self.climate else ""
                ),
            )
        home_grade = (
            sum(journey_grade(self.network, link.legs) for link in links.values())
            / len(links)
            if links
            else 1.0
        )
        return NetworkView(
            day=self.day,
            home=colony_id,
            links=links,
            caravans=tuple(c for c in self.caravans if c.home == colony_id),
            # No climate means no calendar in the view at all: a steward in a
            # seasonless world must behave exactly as it did before there was
            # a year, which is what makes it the control case.
            date=self.date if self.climate else None,
            weather=self.weather,
            forecast=(
                self.climate.forecast(self.day, FORECAST_DAYS) if self.climate else ()
            ),
            coming_season=(
                self.climate.coming_season(self.day) if self.climate else None
            ),
            outlook=(
                self.climate.outlook(self.day, home_grade) if self.climate else ""
            ),
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

        encounter = raid(self.rng, den, caravan.cargo, caravan.escorted, self.day)
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

    def _progress(self, caravan: Caravan) -> float:
        """How much of a day's travel this caravan gets done today.

        One in fair weather. Less in bad, by however much of it the road it is
        on fails to keep off. Nothing at all when the road is shut: it sits the
        storm out and arrives late rather than arriving on time in a blizzard.
        """
        if self.climate is None:
            return 1.0
        return self.climate.progress(self.day, journey_grade(self.network, caravan.legs))

    def _advance_caravans(self) -> None:
        for caravan in list(self.caravans):
            if caravan.state == HOME:
                continue
            moved = self._progress(caravan)
            if moved <= 0.0:
                # Stuck: the road it is on is closed today. It is still out
                # there, still carrying what it loaded, and the animals still
                # get their roll -- a camped caravan is not a safe one.
                self._walk_a_day(caravan)
                caravan.days_waited += 1.0
                self.days_waited += 1.0
                self._tally().waited += 1.0
                note = f"waited out the {self.weather.name}"
                waits = sum(1 for line in caravan.ledger if line.startswith("waited"))
                if waits < WAIT_NOTES and (not caravan.ledger or caravan.ledger[-1] != note):
                    caravan.ledger.append(note)
                continue
            self._walk_a_day(caravan)
            caravan.days_left -= moved
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
                self._tally().journeys += 1
                self.log.append(
                    f"day {self.day}: caravan {caravan.id} home to "
                    f"{self.colonies[caravan.home].name} -- "
                    + "; ".join(caravan.ledger)
                )

        self.caravans = [c for c in self.caravans if c.state != HOME]

    def _dispatch(self) -> None:
        """How many caravans a colony runs at once is a question about people:
        a cart is a crew, and a colony will not have more than a fifth of
        itself away from home. A village that has grown can run two; one that
        has been starved down to nothing still gets its one trip for food.

        Where it sends them is unchanged -- wherever its surplus is worth most
        per day on the road, using the prices it saw on its last visit, which
        may well be out of date by now. Anywhere on the road network is
        reachable, not just the next village along, so a colony at the end of a
        chain can still be supplied."""
        out: dict[int, int] = {}
        for caravan in self.caravans:
            out[caravan.home] = out.get(caravan.home, 0) + 1
        for colony in self.colonies:
            away = out.get(colony.id, 0)
            if away >= people.caravans_allowed(colony.population):
                continue

            best = None
            for other in range(len(self.colonies)):
                if other == colony.id:
                    continue
                # Only roads that are open today. A colony does not send a
                # caravan into a blizzard; it waits for the thaw, or takes
                # whatever long way round is still walkable.
                legs = self._open_route(colony.id, other)
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
                # Counted through the forecast, so a trip that the coming week
                # will drag out loses to one that it will not -- which is how
                # the weather moves trade around the map rather than only
                # slowing it down.
                days = 2 * self.forecast_days(legs) + 1
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
                    colony, hazard, at_risk, days, away + 1
                )
                score = (worth - risk) / days
                if best is None or score > best[0]:
                    best = (score, worth - risk, other, legs, cargo, hazard, escorted)

            if best is None or best[1] < MIN_TRIP_WORTH:
                continue

            _, _, other, legs, cargo, hazard, escorted = best
            # Counted in fair-weather days: the sky is applied to each day of
            # travel as it is walked, not folded into the distance.
            plain = travel_days(self.world.terrain, self.network, legs)
            caravan = Caravan(
                id=self._next_caravan_id,
                home=colony.id,
                destination=other,
                legs=legs,
                days_left=plain,
                leg_days=plain,
                dispatched_day=self.day,
                hazard=hazard,
                escorted=escorted,
            )
            self._next_caravan_id += 1
            for good, qty in cargo.items():
                caravan.cargo[good] = colony.storage.remove(good, qty)
            if escorted:
                # Guards are paid for the days they are actually out, weather
                # and all -- a storm on the road is a storm on the payroll.
                wage = colony.purse.withdraw(escort_cost(2 * self.forecast_days(legs) + 1))
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
        caravans_out: int = 1,
    ) -> tuple[bool, float]:
        """Guards, or no guards, and what the risk costs either way.

        Guards cost two things, and a colony has to have both. Coin: a colony
        with a purse buys its way out of the problem and one without takes its
        chances, which is what makes the wolves a reason to earn rather than a
        flat tax on trading. And people: guards are hands that are not at home,
        so a colony pays for them out of the same allowance a second caravan
        would come from. A big colony can do both; a small one is choosing.
        """
        bare = expected_loss(hazard, at_risk)
        if self.wilds is None or hazard <= 0.0:
            return False, bare
        if not people.can_escort(colony.population, caravans_out):
            return False, bare
        wage = escort_cost(days)
        guarded = expected_loss(hazard, at_risk, escorted=True) + wage
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
    weather: bool = True,
    population: bool = True,
) -> Simulation:
    """A world, its roads, its colonies, and whoever is running them.

    `stewards=False` leaves every colony trading on bare scarcity, which is the
    world this sim had before anyone was in charge of one -- and so the control
    case to compare a steward-run economy against. `weather=False` gives the
    same world under an endless temperate sky: the land gives the same every
    day and no road ever shuts, which is the control for the seasons.
    `population=False` is the same kind of thing for people: every colony stays
    the size it was founded, whatever it has been eating.
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
        population_moves=population,
        wilds=populate(world, seed) if wildlife else None,
        climate=Climate(seed) if weather else None,
        rng=random.Random(seed ^ 0xD00D),
    )
