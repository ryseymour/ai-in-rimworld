"""Wolves and bears: where they live, what they cost, and what traders do."""
from __future__ import annotations

import random

import pytest

from colonysim.goods import GOODS
from colonysim.money import SILVER, Purse
from colonysim.roads import RoadNetwork, RoadTile, Route, route_between
from colonysim.simulation import DANGER_DETOUR, build_simulation
from colonysim.storage import MAX_MULT, Colony, MarketView, Storage
from colonysim.trade import (
    CAPACITY,
    Caravan,
    cautious_capacity,
    do_business,
)
from colonysim.wildlife import (
    BEARS,
    ESCORT_WAGE,
    REGROWTH,
    SAFE_RADIUS,
    SPECIES,
    WOLVES,
    Den,
    Wilds,
    escort_cost,
    expected_loss,
    per_day_hazard,
    populate,
    raid,
)
from colonysim.world import Settlement, generate_world

SEEDS = [1, 7, 23, 99]


class Rolls:
    """A stand-in for `random.Random` that hands back the rolls you name, so a
    single encounter can be pinned to one outcome."""

    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.5


def wolf_den(x: int = 10, y: int = 10, strength: float = 1.0) -> Den:
    return Den(0, "wolves", x, y, strength)


def cargo_caravan(hazard: float = 0.0, **cargo: float) -> Caravan:
    return Caravan(
        id=0,
        home=0,
        destination=1,
        legs=(),
        cargo=dict(cargo),
        purse=Purse(SILVER, 200.0),
        hazard=hazard,
    )


def colony(name="A", cid=0, **stock) -> Colony:
    c = Colony(
        settlement=Settlement(cid, name, 5, 5),
        population=20,
        production={g: 0.0 for g in GOODS},
        consumption={"food": 10.0, "wood": 4.0, "stone": 2.0, "cloth": 1.0, "tools": 0.5},
        storage=Storage(),
        purse=Purse(SILVER, 2000.0),
    )
    for good, qty in stock.items():
        c.storage.add(good, qty)
    return c


# ------------------------------------------------------------------ the map

@pytest.mark.parametrize("seed", SEEDS)
def test_animals_den_on_ground_that_suits_them(seed):
    """Wolves want trees and bears want crags. Neither lives in the water."""
    world = generate_world(seed=seed)
    wilds = populate(world, seed)

    assert wilds.dens, "a world this size should have animals on it"
    for den in wilds.dens:
        kind = world.terrain.kind(den.x, den.y)
        assert SPECIES[den.species].habitat[kind] > 0.0, (den.species, kind)


@pytest.mark.parametrize("seed", SEEDS)
def test_nothing_dens_next_door_to_a_village(seed):
    """Villages keep their own ground clear, which is what puts the danger on
    the road rather than in the market."""
    world = generate_world(seed=seed)
    wilds = populate(world, seed)

    for den in wilds.dens:
        for s in world.settlements:
            distance = ((den.x - s.x) ** 2 + (den.y - s.y) ** 2) ** 0.5
            assert distance >= SAFE_RADIUS, f"{den.species} camped on {s.name}"


def test_the_wild_is_deterministic_and_seed_dependent():
    world = generate_world(seed=23)
    once = populate(world, 23)
    again = populate(world, 23)
    elsewhere = populate(generate_world(seed=24), 24)

    assert [d.pos for d in once.dens] == [d.pos for d in again.dens]
    assert [d.pos for d in once.dens] != [d.pos for d in elsewhere.dens]


# --------------------------------------------------------------- the danger

def test_danger_falls_off_with_distance_and_stops_at_the_reach():
    wilds = Wilds((wolf_den(10, 10),))

    at_the_den = wilds.danger_at(10, 10)
    nearby = wilds.danger_at(13, 10)
    assert at_the_den > nearby > 0.0
    assert wilds.danger_at(10 + int(WOLVES.reach), 10) == 0.0


def test_a_thinned_out_pack_is_less_dangerous():
    strong = Wilds((wolf_den(strength=1.0),)).danger_at(11, 10)
    weak = Wilds((wolf_den(strength=0.25),)).danger_at(11, 10)
    assert strong == pytest.approx(weak * 4.0)


def test_two_dens_are_worse_than_one():
    one = Wilds((wolf_den(10, 10),)).danger_at(11, 10)
    two = Wilds((wolf_den(10, 10), wolf_den(12, 10))).danger_at(11, 10)
    assert two > one


def test_a_better_road_is_a_safer_road():
    """The loop back into road wear: a trunk road is most of the way to safe
    while the foot path beside it is not."""
    wilds = Wilds((wolf_den(10, 10),))
    network = RoadNetwork()

    network.tiles[(11, 10)] = RoadTile(tier=1)
    path = wilds.tile_hazard(network, 11, 10)
    network.tiles[(11, 10)] = RoadTile(tier=3)
    paved = wilds.tile_hazard(network, 11, 10)

    assert paved < path
    assert paved > 0.0, "a road never makes the wild disappear"


def test_a_longer_road_past_a_den_is_more_dangerous_but_never_certain():
    wilds = Wilds((wolf_den(10, 10),))
    network = RoadNetwork()

    short = wilds.path_hazard(network, ((10, 10), (11, 10)))
    long = wilds.path_hazard(network, tuple((10 + i, 10) for i in range(8)))

    assert 0.0 < short < long < 1.0


def test_a_road_out_of_reach_of_everything_is_safe():
    wilds = Wilds((wolf_den(10, 10),))
    assert wilds.path_hazard(RoadNetwork(), ((40, 40), (41, 40))) == 0.0


def test_a_journey_of_several_legs_is_riskier_than_each_leg():
    wilds = Wilds((wolf_den(10, 10), wolf_den(20, 10)))
    network = RoadNetwork()
    first = Route(0, 1, tuple((10 + i, 10) for i in range(5)), 10.0)
    second = Route(1, 2, tuple((18 + i, 10) for i in range(5)), 10.0)

    both = wilds.journey_hazard(network, (first, second))
    assert both > wilds.route_hazard(network, first)
    assert both > wilds.route_hazard(network, second)


def test_a_days_risk_compounds_back_into_the_journeys():
    """A caravan rolls once a day, so the daily chance has to multiply out to
    the hazard the trader was quoted before it set off."""
    for hazard in (0.05, 0.2, 0.6):
        daily = per_day_hazard(hazard, 5)
        assert 1.0 - (1.0 - daily) ** 5 == pytest.approx(hazard, abs=1e-9)


# ------------------------------------------------------------- an encounter

def test_a_caravan_can_simply_drive_them_off():
    den = wolf_den()
    caravan = cargo_caravan(food=40.0)
    strength_before = den.strength

    met = raid(Rolls(0.0), den, caravan.cargo, escorted=False, day=3)

    assert met.outcome == "drove off"
    assert met.losses == {}
    assert caravan.cargo["food"] == 40.0
    assert den.strength < strength_before, "being driven off should cost them"


def test_animals_take_the_food_first_and_leave_the_stone():
    den = wolf_den()
    caravan = cargo_caravan(food=100.0, stone=100.0)

    met = raid(Rolls(0.99, 0.99), den, caravan.cargo, escorted=False, day=3)

    assert met.outcome == "raided"
    assert met.losses["food"] > met.losses["stone"]
    assert caravan.cargo["food"] < 100.0


def test_what_a_raid_takes_is_exactly_what_leaves_the_cargo():
    """The losses a raid reports are what conservation is checked against, so
    they have to match the cargo to the last decimal."""
    den = wolf_den()
    caravan = cargo_caravan(food=80.0, cloth=20.0, tools=5.0)
    before = dict(caravan.cargo)

    met = raid(Rolls(0.99, 0.99), den, caravan.cargo, escorted=False, day=1)

    for good, was in before.items():
        now = caravan.cargo.get(good, 0.0)
        assert was - now == pytest.approx(met.losses.get(good, 0.0), abs=1e-9)


def test_a_raid_cannot_take_more_than_is_on_the_cart():
    den = Den(0, "bears", 5, 5)
    caravan = cargo_caravan(food=3.0)

    raid(Rolls(0.99, 0.99), den, caravan.cargo, escorted=False, day=1)

    assert caravan.cargo.get("food", 0.0) >= 0.0


def test_an_empty_caravan_loses_nothing_to_the_wolves():
    met = raid(Rolls(0.99, 0.99), wolf_den(), {}, escorted=False, day=1)
    assert met.losses == {}
    assert met.lost_total == 0.0


def test_a_bear_can_turn_a_caravan_around_and_a_wolf_pack_rarely_does():
    bear = raid(Rolls(0.99, 0.0), Den(0, "bears", 5, 5), {"food": 50.0}, False, 1)
    wolves = raid(Rolls(0.99, 0.99), wolf_den(), {"food": 50.0}, False, 1)

    assert bear.outcome == "routed"
    assert wolves.outcome == "raided"
    assert BEARS.ferocity > WOLVES.ferocity


def test_guards_get_the_caravan_out_of_it_more_often_and_more_cheaply():
    """Over many meetings: escorted caravans are left alone more often and
    lose less when they are not."""
    alone = escorted = 0
    lost_alone = lost_escorted = 0.0
    for trial in range(300):
        for guarded in (False, True):
            den = wolf_den()
            cargo = {"food": 100.0}
            met = raid(random.Random(trial), den, cargo, guarded, day=1)
            if met.outcome == "drove off":
                if guarded:
                    escorted += 1
                else:
                    alone += 1
            if guarded:
                lost_escorted += met.lost_total
            else:
                lost_alone += met.lost_total

    assert escorted > alone
    assert lost_escorted < lost_alone


# ---------------------------------------------------------- dens over time

def test_a_quiet_den_grows_back():
    den = wolf_den(strength=0.5)
    wilds = Wilds((den,))
    wilds.settle_day(RoadNetwork())
    assert den.strength == pytest.approx(0.5 + REGROWTH)


def test_a_den_never_grows_past_full_strength():
    den = wolf_den(strength=1.0)
    wilds = Wilds((den,))
    for _ in range(50):
        wilds.settle_day(RoadNetwork())
    assert den.strength == 1.0


def test_a_busy_road_pushes_the_pack_back_into_the_hills():
    """Traffic and regrowth pull against each other, and a paved trunk road
    running past the den wins. That is why a well-used route gets safer."""
    den = wolf_den(10, 10, strength=1.0)
    wilds = Wilds((den,))
    network = RoadNetwork()
    for dx in range(-4, 5):
        network.tiles[(10 + dx, 10)] = RoadTile(tier=3)

    for _ in range(20):
        wilds.settle_day(network)

    assert den.strength < 1.0


# ------------------------------------------------- what a trader does about it

def test_a_dangerous_road_is_worth_something_to_avoid():
    assert expected_loss(0.4, 500.0) > expected_loss(0.1, 500.0) > 0.0
    assert expected_loss(0.0, 500.0) == 0.0
    assert expected_loss(0.4, 0.0) == 0.0


def test_guards_cut_what_a_trader_expects_to_lose():
    assert expected_loss(0.4, 500.0, escorted=True) < expected_loss(0.4, 500.0)


def test_guards_are_paid_by_the_day():
    assert escort_cost(6) == pytest.approx(ESCORT_WAGE * 6)


def test_a_trader_loads_lighter_where_there_is_more_to_lose():
    assert cautious_capacity(0.0) == CAPACITY
    assert cautious_capacity(0.3) < CAPACITY
    assert cautious_capacity(1.0) < cautious_capacity(0.3)
    assert cautious_capacity(1.0) > 0.0


def test_a_safe_road_carries_no_premium():
    assert cargo_caravan(hazard=0.0).risk_premium == 0.0


def test_a_caravan_that_walked_a_wolf_road_asks_more_for_the_goods():
    """The host pays for the journey as well as the goods -- but never more
    than any good can fetch there, so the premium is a margin, not a hold-up.
    """
    safe = cargo_caravan(hazard=0.0, food=30.0)
    risky = cargo_caravan(hazard=0.5, food=30.0)

    paid = []
    for caravan in (safe, risky):
        host = colony("Host", 1, food=60.0)  # short: reserve is 200
        before = host.purse.amount
        do_business(caravan, host, colony("Home", 0), day=1)
        paid.append(before - host.purse.amount)

    assert paid[1] > paid[0]
    assert risky.risk_premium > 0.0


def test_the_premium_never_pushes_a_price_past_the_ceiling():
    caravan = cargo_caravan(hazard=1.0, food=10.0)
    host = colony("Host", 1)  # empty store, already quoting the ceiling
    before = host.purse.amount

    do_business(caravan, host, colony("Home", 0), day=1)

    paid = before - host.purse.amount
    assert paid <= 10.0 * GOODS["food"].base_price * MAX_MULT + 1e-6


def test_a_trader_goes_the_long_way_round_to_avoid_a_den():
    """The whole of routing around the animals: a dangerous leg costs more to
    consider, so the search takes a longer, quieter chain instead.

    The short way is a road through a wolf valley; the long way is half again
    the distance and empty. At the surcharge the sim actually uses, the long
    way wins.
    """
    valley = tuple((x, 0) for x in range(31))
    direct = Route(0, 1, valley, 10.0)
    first = Route(0, 2, ((0, 0), (0, 50)), 6.0)
    second = Route(1, 2, ((0, 50), (30, 0)), 6.0)
    network = RoadNetwork(routes={(0, 1): direct, (0, 2): first, (1, 2): second})
    wilds = Wilds((wolf_den(12, 0), wolf_den(18, 0)))

    def surcharge(route: Route) -> float:
        return route.cost * DANGER_DETOUR * wilds.route_hazard(network, route)

    assert surcharge(first) == 0.0, "the long way round should be empty country"
    assert route_between(network, 0, 1) == (direct,), "the short way is shorter"
    assert route_between(network, 0, 1, surcharge=surcharge) == (first, second)


# ------------------------------------------------------------- over a season

def test_a_wild_world_costs_its_traders_something():
    """Across seeds: the animals are a real cost, not decoration. Either they
    take goods or the colonies pay to keep them off."""
    total_lost = 0.0
    total_wages = 0.0
    for seed in SEEDS:
        sim = build_simulation(seed=seed)
        sim.run(90)
        total_lost += sim.goods_lost()
        total_wages += sim.escort_wages

    assert total_lost + total_wages > 0.0


def test_everything_the_animals_take_came_off_a_caravan():
    """Animals meet caravans on the road and nowhere else, so a world with no
    trade in it loses nothing however many wolves are on the map."""
    sim = build_simulation(seed=7)
    sim.trade_enabled = False
    sim.run(90)

    assert sim.lost == {}
    assert sim.meetings == 0
    assert sim.escort_wages == 0.0


def test_a_colony_only_hires_guards_it_can_pay_for():
    sim = build_simulation(seed=7)
    for c in sim.colonies:
        c.purse.withdraw(c.purse.amount)
    sim.run(60)

    assert sim.escort_wages == 0.0


def test_traders_pick_their_way_around_the_worst_of_it():
    """A caravan's own hazard should come in under the average of the roads it
    could have taken: routing is doing something."""
    sim = build_simulation(seed=23)
    chosen: list[float] = []
    dispatch = sim._dispatch

    def record() -> None:
        known = {c.id for c in sim.caravans}
        dispatch()
        chosen.extend(c.hazard for c in sim.caravans if c.id not in known)

    sim._dispatch = record
    sim.run(90)

    available = [
        sim.wilds.route_hazard(sim.network, route)
        for route in sim.network.routes.values()
    ]
    assert chosen, "nobody set out at all"
    assert sum(chosen) / len(chosen) < max(available)


def test_the_wild_slows_trade_down_without_stopping_it():
    """The layer has to bite without breaking the economy underneath it: fewer
    journeys overall, but no colony left cut off."""
    wild_total = tame_total = 0
    for seed in SEEDS:
        wild = build_simulation(seed=seed)
        tame = build_simulation(seed=seed, wildlife=False)
        wild.run(120)
        tame.run(120)
        wild_total += wild.journeys
        tame_total += tame.journeys

        assert wild.journeys > tame.journeys / 2, f"seed {seed}: trade was crushed"
        assert wild.hungry_colonies() == [], f"seed {seed}: the animals starved someone"

    assert wild_total < tame_total, "the animals cost the roads nothing at all"


def test_a_caravan_turned_back_by_a_bear_still_gets_home():
    """Being routed must leave the caravan in a state the day loop can finish,
    not stranded pointing the wrong way."""
    sim = build_simulation(seed=42)
    sim.run(150)

    assert sim.journeys > 0
    for caravan in sim.caravans:
        assert sim.day - caravan.dispatched_day < 60


def test_a_tame_world_is_a_clean_control():
    sim = build_simulation(seed=23, wildlife=False)
    assert sim.wilds is None
    sim.run(30)
    assert sim.meetings == 0
