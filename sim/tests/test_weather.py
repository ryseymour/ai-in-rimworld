"""The year: the calendar, what the seasons do to the land, and what the
weather does to the roads."""
from __future__ import annotations

from collections import Counter

import pytest

from colonysim.goods import GOOD_NAMES, GOODS
from colonysim.money import SILVER, Purse
from colonysim.roads import (
    RoadNetwork,
    RoadTile,
    Route,
    journey_grade,
    path_grade,
    route_between,
    route_grade,
    travel_cost,
)
from colonysim.simulation import build_simulation
from colonysim.steward import LEAN_YIELD, SLOW_INTERVAL, Link, NetworkView, Steward
from colonysim.storage import Colony, MarketView, Storage
from colonysim.terrain import generate_terrain
from colonysim.weather import (
    AUTUMN,
    BLIZZARD,
    CLEAR,
    RAIN,
    SEASON_DAYS,
    SEASONS,
    SNOW,
    SPRING,
    STORM,
    SUMMER,
    WINTER,
    YEAR_DAYS,
    Climate,
    Weather,
    date_of,
    season_of,
    seasonal_totals,
    shelter,
)
from colonysim.world import Settlement

SEEDS = [1, 7, 23, 99]


def colony(population: int = 20, **stock: float) -> Colony:
    c = Colony(
        settlement=Settlement(0, "Ashford", 5, 5),
        population=population,
        production={g: 1.0 for g in GOOD_NAMES},
        consumption={g: 0.5 for g in GOOD_NAMES},
        storage=Storage(),
        purse=Purse(SILVER, 500.0),
    )
    for good, qty in stock.items():
        c.storage.add(good, qty)
    return c


# ------------------------------------------------------------------ calendar

def test_the_year_is_four_seasons_and_comes_back_round():
    assert YEAR_DAYS == SEASON_DAYS * 4
    assert date_of(0).season is SPRING
    assert date_of(0).day_of_season == 1
    assert date_of(0).year == 1
    assert season_of(SEASON_DAYS) is SUMMER
    assert season_of(2 * SEASON_DAYS) is AUTUMN
    assert season_of(3 * SEASON_DAYS) is WINTER
    assert season_of(YEAR_DAYS) is SPRING
    assert date_of(YEAR_DAYS).year == 2
    assert date_of(YEAR_DAYS).day_of_season == 1


def test_every_day_of_the_year_lands_in_exactly_one_season():
    seen = Counter(season_of(day).name for day in range(YEAR_DAYS))
    assert set(seen) == {s.name for s in SEASONS}
    assert set(seen.values()) == {SEASON_DAYS}


def test_a_season_has_a_beginning_a_middle_and_an_end():
    parts = [date_of(day).part for day in range(SEASON_DAYS)]
    assert parts[0] == "early"
    assert parts[-1] == "late"
    assert "mid" in parts
    assert str(date_of(2 * SEASON_DAYS)) == "early autumn, year 1"


# ------------------------------------------------------------- what it gives

def test_a_year_gives_exactly_what_the_land_would_have_given():
    """The invariant the whole calendar rests on.

    If a year's growth multipliers did not average to one, adding seasons
    would quietly recalibrate the world's output and every claim about trade
    would be measuring the recalibration instead.
    """
    for good, total in seasonal_totals().items():
        assert total == pytest.approx(len(SEASONS)), good


def test_autumn_is_the_harvest_and_winter_is_not():
    assert AUTUMN.yields("food") > SUMMER.yields("food") > SPRING.yields("food")
    assert WINTER.yields("food") < 0.5
    for good in ("food", "wood", "stone", "cloth"):
        assert WINTER.yields(good) < LEAN_YIELD, good


def test_tools_are_the_winter_trade():
    """Indoor work barely notices the season, which is what gives a colony
    something to sell when its fields are dead."""
    assert WINTER.yields("tools") >= 1.0
    assert all(abs(s.yields("tools") - 1.0) < 0.1 for s in SEASONS)


def test_a_colony_makes_less_in_winter_and_more_in_autumn():
    c = colony()
    plain, _ = c.live_day()
    autumn, _ = c.live_day(AUTUMN.growth)
    winter, _ = c.live_day(WINTER.growth)
    assert autumn["food"] > plain["food"] > winter["food"]
    assert winter["food"] == pytest.approx(plain["food"] * WINTER.yields("food"))


def test_a_full_year_of_seasons_produces_what_a_seasonless_year_produces():
    seasoned = colony()
    flat = colony()
    for day in range(YEAR_DAYS):
        seasoned.live_day(season_of(day).growth)
        flat.live_day()
    for good in GOOD_NAMES:
        assert seasoned.storage.get(good) == pytest.approx(flat.storage.get(good))


def test_no_season_at_all_is_exactly_the_old_behaviour():
    c = colony()
    assert c.output("food", None) == c.output("food")
    assert c.output("food", {}) == c.output("food")


# ---------------------------------------------------------- roads and the sky

def test_a_better_road_keeps_more_weather_off():
    assert shelter(0.0) < shelter(1.0) < shelter(2.0) < shelter(3.0)
    assert shelter(1.5) == pytest.approx((shelter(1.0) + shelter(2.0)) / 2)
    assert shelter(9.0) == shelter(3.0)


def test_fair_weather_costs_nothing_on_any_road():
    assert all(CLEAR.slowdown(grade) == 1.0 for grade in (0, 1, 2, 3))
    assert not any(CLEAR.shuts(grade) for grade in (0, 1, 2, 3))
    assert CLEAR.is_fair


def test_bad_weather_hurts_a_poor_road_more_than_a_paved_one():
    for weather in (RAIN, SNOW, STORM, BLIZZARD):
        assert weather.slowdown(1.0) > weather.slowdown(2.0) > weather.slowdown(3.0)
        assert weather.slowdown(3.0) > 1.0, "paved is sheltered, not immune"


def test_what_shuts_a_road_and_what_only_slows_it():
    """The line the whole feature turns on: a worn road trades through weather
    that stops a foot path."""
    assert STORM.shuts(1.0) and not STORM.shuts(2.0)
    assert BLIZZARD.shuts(1.0) and not BLIZZARD.shuts(2.0)
    assert not SNOW.shuts(1.0), "snow slows, it does not close"
    assert SNOW.slowdown(1.0) > 1.5
    assert not RAIN.shuts(0.0)


def test_a_paved_route_is_never_shut():
    assert not any(w.shuts(3.0) for w in (STORM, SNOW, BLIZZARD, RAIN))


def test_weather_makes_a_tile_dearer_to_cross():
    terrain = generate_terrain(20, 20, seed=3)
    network = RoadNetwork()
    path = tuple((x, 5) for x in range(2, 10))
    for tile in path:
        network.tiles[tile] = RoadTile(tier=1)

    fair = travel_cost(terrain, network, path)
    snowed = travel_cost(terrain, network, path, SNOW.slowdown)
    assert snowed > fair
    assert snowed == pytest.approx(fair * SNOW.slowdown(1.0))


def test_a_paved_stretch_shelters_the_caravan_on_it():
    """Slowdown is asked per tile, so a route is only as exposed as its
    stretches -- not as its average pretended to be."""
    terrain = generate_terrain(20, 20, seed=3)
    path = tuple((x, 5) for x in range(2, 10))
    rough = RoadNetwork(tiles={t: RoadTile(tier=1) for t in path})
    paved = RoadNetwork(tiles={t: RoadTile(tier=3) for t in path})
    assert travel_cost(terrain, paved, path, STORM.slowdown) < travel_cost(
        terrain, rough, path, STORM.slowdown
    )


# ----------------------------------------------------------------- the grade

def test_a_routes_grade_is_the_mean_tier_along_it():
    path = ((0, 0), (1, 0), (2, 0), (3, 0))
    network = RoadNetwork(
        tiles={(0, 0): RoadTile(1), (1, 0): RoadTile(1), (2, 0): RoadTile(3), (3, 0): RoadTile(3)}
    )
    assert path_grade(network, path) == pytest.approx(2.0)
    assert route_grade(network, Route(0, 1, path, 1.0)) == pytest.approx(2.0)
    assert journey_grade(network, (Route(0, 1, path, 1.0),)) == pytest.approx(2.0)
    assert path_grade(network, ()) == 0.0


def test_open_country_grades_zero():
    assert path_grade(RoadNetwork(), ((0, 0), (1, 0))) == 0.0


# ------------------------------------------------------------ closed routes

def _line(a: int, b: int, y: int) -> Route:
    return Route(a, b, tuple((x, y) for x in range(10)), cost=10.0)


def test_a_shut_leg_is_no_way_through_at_all():
    """Closure takes a leg out of the graph rather than making it dear, so the
    search finds whatever open chain is left instead of walking through snow."""
    short = _line(0, 1, 0)
    long_a, long_b = _line(0, 2, 5), _line(1, 2, 6)
    network = RoadNetwork(routes={(0, 1): short, (0, 2): long_a, (1, 2): long_b})

    assert route_between(network, 0, 1) == (short,)
    detour = route_between(network, 0, 1, blocked=lambda r: r is short)
    assert detour == (long_a, long_b)


def test_weather_can_cut_a_colony_off_entirely():
    only = _line(0, 1, 0)
    network = RoadNetwork(routes={(0, 1): only})
    assert route_between(network, 0, 1, blocked=lambda r: True) == ()


# -------------------------------------------------------------- the forecast

@pytest.mark.parametrize("seed", SEEDS)
def test_the_same_seed_gives_the_same_year(seed):
    a, b = Climate(seed), Climate(seed)
    assert [a.on(d).name for d in range(YEAR_DAYS)] == [
        b.on(d).name for d in range(YEAR_DAYS)
    ]


def test_two_seeds_do_not_give_the_same_year():
    assert [Climate(1).on(d).name for d in range(YEAR_DAYS)] != [
        Climate(2).on(d).name for d in range(YEAR_DAYS)
    ]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_forecast_is_what_actually_happens(seed):
    """Asking early must not change the answer, or a steward planning ahead
    would be planning against a different world from the one it lives in."""
    early = Climate(seed)
    ahead = early.forecast(20, days=7)
    assert [w.name for w in ahead] == [early.on(20 + i).name for i in range(7)]

    fresh = Climate(seed)
    for day in range(27):  # walked to day by day rather than jumped to
        fresh.on(day)
    assert [fresh.on(20 + i).name for i in range(7)] == [w.name for w in ahead]


@pytest.mark.parametrize("seed", SEEDS)
def test_weather_comes_in_spells_rather_than_flickering(seed):
    climate = Climate(seed)
    days = [climate.on(d) for d in range(600)]
    same = sum(1 for a, b in zip(days, days[1:]) if a is b)
    assert same / len(days) > 0.4, "the sky should hold for more than a day"


@pytest.mark.parametrize("seed", SEEDS)
def test_blizzards_are_a_winter_thing(seed):
    climate = Climate(seed)
    winter = sum(
        1
        for d in range(20 * YEAR_DAYS)
        if climate.on(d) is BLIZZARD and season_of(d) is WINTER
    )
    total = sum(1 for d in range(20 * YEAR_DAYS) if climate.on(d) is BLIZZARD)
    assert total > 0
    assert winter / total > 0.8, "a blizzard in high summer is a bug"


@pytest.mark.parametrize("seed", SEEDS)
def test_autumn_is_the_storm_season(seed):
    climate = Climate(seed)
    days = 20 * YEAR_DAYS
    storms = Counter(
        season_of(d).name for d in range(days) if climate.on(d) is STORM
    )
    assert storms["autumn"] > storms["summer"]


# ------------------------------------------------------- journeys in weather

def test_a_journey_takes_longer_through_bad_weather():
    climate = Climate(4)
    for day in range(200):
        plain = 4.0
        assert climate.journey_days(day, plain, grade=1.0) >= plain


def test_a_shut_road_makes_a_journey_take_its_worst_case():
    """Not an ever-growing estimate: a road the weather has closed should
    simply lose to any open one."""

    class NeverOpens(Climate):
        def on(self, day: int) -> Weather:
            return BLIZZARD

    climate = NeverOpens(0)
    assert climate.journey_days(0, 4.0, grade=1.0) == pytest.approx(4.0 * 5.0)


def test_a_paved_road_gets_there_sooner_than_a_path():
    climate = Climate(11)
    slow = sum(climate.journey_days(d, 4.0, grade=1.0) for d in range(YEAR_DAYS))
    fast = sum(climate.journey_days(d, 4.0, grade=3.0) for d in range(YEAR_DAYS))
    assert fast < slow


def test_fair_weather_adds_nothing():
    class Fair(Climate):
        def on(self, day: int) -> Weather:
            return CLEAR

    assert Fair(0).journey_days(0, 5.0, grade=1.0) == pytest.approx(5.0)


# ------------------------------------------------------------ in the world

@pytest.mark.parametrize("seed", SEEDS)
def test_a_world_with_no_climate_is_exactly_the_old_world(seed):
    """The control case. No seasons means no calendar anywhere in the sim, not
    a calendar nobody mentions."""
    sim = build_simulation(seed, 3, 60, 30, weather=False)
    sim.run(YEAR_DAYS)
    assert sim.climate is None
    assert sim.days_roads_shut == 0
    assert sim.days_waited == 0.0
    assert sim.growth() is None
    assert sim.weather is CLEAR
    assert not sim.shut_routes()
    view = sim.network_view(0)
    assert view.coming_season is None
    assert view.date is None
    assert all(link.open for link in view.links.values())


@pytest.mark.parametrize("seed", SEEDS)
def test_a_year_passes_and_the_roads_shut_sometimes(seed):
    sim = build_simulation(seed, 4, 70, 35)
    sim.run(3 * YEAR_DAYS)
    assert sim.date.year == 4
    assert 0 < sim.days_roads_shut < sim.day, "weather should bite, not stop the world"
    assert set(sim.tallies) == {s.name for s in SEASONS}
    assert all(t.days == 3 * SEASON_DAYS for t in sim.tallies.values())


@pytest.mark.parametrize("seed", SEEDS)
def test_the_harvest_is_in_autumn_and_the_hungry_season_is_winter(seed):
    sim = build_simulation(seed, 4, 70, 35)
    sim.run(4 * YEAR_DAYS)
    made = {name: t.produced.get("food", 0.0) for name, t in sim.tallies.items()}
    assert made["autumn"] == max(made.values())
    assert made["winter"] == min(made.values())
    assert made["autumn"] > 4 * made["winter"]


@pytest.mark.parametrize("seed", SEEDS)
def test_food_is_dearest_in_the_hungry_gap_and_cheapest_after_the_harvest(seed):
    """The whole point of a year in a trading game: the same good is worth
    different money in different months, so when you move it matters.

    Spring is the dearest, not winter -- a colony goes into winter on a full
    granary and comes out of it on an empty one, so the hungry gap is the far
    side of the cold rather than the cold itself.
    """
    sim = build_simulation(seed, 4, 70, 35)
    sim.run(4 * YEAR_DAYS)
    prices = {name: t.mean_price("food") for name, t in sim.tallies.items()}
    assert prices["spring"] == max(prices.values())
    assert prices["autumn"] < prices["summer"] < prices["spring"]
    assert max(prices.values()) / min(prices.values()) > 1.1, "a flat year"


@pytest.mark.parametrize("seed", SEEDS)
def test_trade_still_conserves_goods_and_coin_through_the_seasons(seed):
    """Weather costs time; it must never cost a single unit of anything. If it
    did, the conservation check that guards the whole economy would have been
    quietly loosened by adding a calendar."""
    sim = build_simulation(seed, 4, 70, 35)
    start = sim.goods_in_world()
    coin = sim.coin_in_world()
    sim.run(2 * YEAR_DAYS)

    for good in GOOD_NAMES:
        expected = (
            start[good]
            + sim.produced.get(good, 0.0)
            - sim.consumed.get(good, 0.0)
            - sim.lost.get(good, 0.0)
        )
        assert sim.goods_in_world()[good] == pytest.approx(expected, abs=1e-6), good
    assert sim.coin_in_world() + sim.escort_wages == pytest.approx(coin, abs=1e-6)


@pytest.mark.parametrize("seed", SEEDS)
def test_nobody_is_left_stranded_by_the_weather(seed):
    sim = build_simulation(seed, 4, 70, 35)
    sim.run(3 * YEAR_DAYS)
    for caravan in sim.caravans:
        assert sim.day - caravan.dispatched_day < 2 * YEAR_DAYS, "stuck on the road"


@pytest.mark.parametrize("seed", SEEDS)
def test_the_same_seed_runs_the_same_year_twice(seed):
    a = build_simulation(seed, 4, 70, 35)
    b = build_simulation(seed, 4, 70, 35)
    a.run(2 * YEAR_DAYS)
    b.run(2 * YEAR_DAYS)
    assert (a.journeys, a.days_waited, a.days_roads_shut) == (
        b.journeys,
        b.days_waited,
        b.days_roads_shut,
    )


def test_the_weather_costs_the_roads_time_and_never_goods():
    """Weather is friction on the calendar, not a tax on the shelves. It takes
    days off caravans and shuts roads, and takes nothing off anyone -- the
    animals are still the only thing in the sim that destroys goods.

    Note what it does *not* assert: that a year of weather means less trade.
    It usually means more, because a colony laying in stores before winter
    bids for them, and that pulls caravans onto the roads. The seasons move
    trade around the year rather than simply slowing it down.
    """
    calm = build_simulation(23, 4, 70, 35, weather=False)
    stormy = build_simulation(23, 4, 70, 35)
    calm.run(3 * YEAR_DAYS)
    stormy.run(3 * YEAR_DAYS)

    assert stormy.days_waited > 0
    assert stormy.days_roads_shut > 0
    assert stormy.journeys > calm.journeys * 0.5, "it must not stop trade"
    assert not stormy.hungry_colonies()

    # A year of weather over a world with no animals in it destroys nothing at
    # all, which is the sharpest way to say weather never eats anything.
    tame = build_simulation(23, 4, 70, 35, wildlife=False)
    tame.run(3 * YEAR_DAYS)
    assert tame.days_waited > 0
    assert tame.goods_lost() == 0.0


def test_a_caravan_on_a_shut_road_sits_still():
    sim = build_simulation(23, 4, 70, 35)
    sim.run(2 * YEAR_DAYS)
    assert sim.days_waited > 0

    # Every day waited is a day nobody moved, and no cargo went anywhere.
    sim.climate = _AlwaysBlizzard(23)
    while not sim.caravans:
        sim.step_day()
    caravan = sim.caravans[0]
    before = (caravan.days_left, dict(caravan.cargo), caravan.days_waited)
    sim.step_day()
    assert caravan.days_left == before[0]
    assert caravan.days_waited == before[2] + 1


class _AlwaysBlizzard(Climate):
    def on(self, day: int) -> Weather:
        return BLIZZARD


def test_nobody_sets_out_onto_a_shut_road():
    sim = build_simulation(23, 4, 70, 35)
    sim.run(YEAR_DAYS)
    sim.climate = _AlwaysBlizzard(23)
    sim.caravans.clear()
    for _ in range(10):
        sim.step_day()
        assert not sim.caravans, "dispatched into a blizzard"


# ----------------------------------------------------- what a steward sees

def test_a_steward_sees_the_date_the_sky_and_what_is_shut():
    sim = build_simulation(23, 4, 70, 35)
    sim.run(3 * SEASON_DAYS + 5)  # somewhere in the first winter
    view = sim.network_view(0)
    assert view.date is not None and view.season is WINTER
    assert len(view.forecast) == 7
    assert view.forecast[0] is sim.weather
    assert view.outlook
    assert len(view.open_links()) + len(view.shut()) == len(view.links)
    sim.stewards[0].review(view)
    brief = sim.stewards[0].brief()
    assert "winter" in brief
    assert "the sky:" in brief


def test_a_link_knows_how_long_the_road_really_takes_this_week():
    sim = build_simulation(23, 4, 70, 35)
    sim.run(3 * SEASON_DAYS + 2)
    for link in sim.network_view(0).open_links():
        assert link.weather_days >= link.days
        assert link.delay == pytest.approx(link.weather_days - link.days)


def test_a_shut_neighbour_is_still_on_the_map():
    """Dropping the link would be worse than closing the road: a steward that
    cannot see a snowed-in village cannot plan for the thaw."""
    sim = build_simulation(23, 4, 70, 35)
    sim.run(YEAR_DAYS)
    sim.climate = _AlwaysBlizzard(23)
    sim._open_today.clear()
    sim._routes_today.clear()
    view = sim.network_view(0)
    assert view.links, "the villages have not gone anywhere"
    assert not view.open_links()
    assert view.shut() == view.neighbours()
    sim.stewards[0].review(view)
    assert "shut today" in sim.stewards[0].brief()


def _link(cid: int = 1) -> Link:
    return Link(
        colony=cid,
        name="Brackwater",
        days=3.0,
        hazard=0.0,
        tier=1.0,
        legs=(),
        market=MarketView.unvisited(),
    )


def test_a_link_with_no_weather_is_a_plain_road():
    link = _link()
    assert link.open
    assert link.weather_days == link.days
    assert link.delay == 0.0


def test_a_steward_fills_the_granary_before_a_season_that_makes_nothing():
    """Laying in stores is the seasonal decision: the reserve goes up, which
    both stops the colony selling what it is about to need and -- because
    scarcity is measured against the reserve -- puts the price up until
    somebody hauls more in."""
    # Sitting exactly on its buffer, so the seasonal term is the only thing
    # with anything to say about the granary.
    before_winter = Steward(colony(food=10.0))
    before_summer = Steward(colony(food=10.0))
    for _ in range(SLOW_INTERVAL * 3):
        before_winter.review(NetworkView(day=40, home=0, links={}, coming_season=WINTER))
        before_summer.review(NetworkView(day=10, home=0, links={}, coming_season=SUMMER))

    assert before_winter.colony.reserve_days("food") > GOODS["food"].buffer_days
    assert before_winter.colony.reserve_days("food") > before_summer.colony.reserve_days(
        "food"
    )
    assert any("winter is coming" in line for line in before_winter.log)


def test_a_steward_with_no_calendar_keeps_the_usual_buffers():
    """The control: the seasonal reserve must not fire in a world that has no
    seasons in it."""
    steward = Steward(colony(food=10.0))
    for _ in range(SLOW_INTERVAL * 3):
        steward.review(NetworkView(day=40, home=0, links={}))
    assert steward.view is not None and steward.view.coming_season is None
    assert steward.colony.reserve_days("food") == pytest.approx(
        GOODS["food"].buffer_days
    )
