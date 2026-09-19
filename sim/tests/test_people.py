"""Population: what food does to how many people a colony has.

Two halves. The unit half pins the rules down one at a time on a colony built
to order, so a failure says which rule broke. The season half runs whole worlds
and asks the only question the feature exists to answer: does it now cost a
colony something real to be cut off from food?
"""
from __future__ import annotations

import pytest

from colonysim import people
from colonysim.goods import GOODS
from colonysim.money import SILVER, Purse
from colonysim.people import (
    BIRTH_RATE,
    CREW,
    GUARDS,
    HUNGER_RATE,
    LAND_ELASTICITY,
    LEAN,
    MIN_POPULATION,
    PLENTY,
    ROAD_SHARE,
)
from colonysim.simulation import build_simulation
from colonysim.storage import Colony
from colonysim.world import Settlement

SEEDS = [1, 7, 23, 99]
DAYS = 150


def colony(population: float = 20.0, food: float | None = None, **rates) -> Colony:
    """A colony that eats, makes nothing, and holds exactly one buffer of food
    unless told otherwise. Production is empty so a test can move the stores
    without the land quietly refilling them."""
    consumption = {"food": 0.55 * population, "wood": 0.18 * population}
    c = Colony(
        settlement=Settlement(0, "Testhollow", 5, 5),
        population=population,
        production={good: 0.0 for good in GOODS},
        consumption={**consumption, **rates},
        purse=Purse(SILVER, 500.0),
    )
    buffer = c.consumption["food"] * GOODS["food"].buffer_days
    c.storage.add("food", buffer if food is None else food)
    return c


def buffers(c: Colony, covers: float) -> float:
    """That many buffers of food, in units."""
    return covers * c.consumption["food"] * GOODS["food"].buffer_days


# ----------------------------------------------------------------- the rules

def test_a_fed_colony_with_stores_to_spare_grows():
    c = colony()
    c.storage.add("food", buffers(c, PLENTY + 1.0) - c.storage.get("food"))
    change = people.step(c, ration=1.0)

    assert change.born > 0
    assert change.starved == 0 and change.left == 0
    assert c.population > 20.0


def test_a_fed_colony_with_no_stores_to_spare_does_not_grow():
    """Being fed is not the same as being comfortable. A colony living hand to
    mouth stays the size it is -- which is what stops every colony in a
    calibrated world growing forever just because the sum works out."""
    c = colony()  # exactly one buffer, which is below PLENTY
    assert people.food_cover(c) < PLENTY
    change = people.step(c, ration=1.0)

    assert change.born == 0 and change.net == 0


def test_a_colony_that_cannot_feed_everyone_loses_people():
    c = colony(food=0.0)
    for _ in range(30):
        people.step(c, ration=0.0)

    assert c.population < 20.0
    assert c.starved > 0


def test_hunger_is_judged_over_a_fortnight_not_a_day():
    """One empty day is not a famine. The colony has to have been going
    without for a while before anyone dies of it, so a caravan that is two
    days late does not kill anybody."""
    one_bad_day = colony(food=0.0)
    people.step(one_bad_day, ration=0.0)

    a_bad_month = colony(food=0.0)
    for _ in range(30):
        people.step(a_bad_month, ration=0.0)

    assert one_bad_day.starved < 0.1
    assert a_bad_month.starved > 30 * one_bad_day.starved


def test_thin_stores_lose_a_trickle_before_anyone_goes_hungry():
    """The gentler of the two ways to lose people, and the one that fires
    first: everyone is still eating, the granary just looks bad."""
    c = colony(food=0.0)
    c.storage.add("food", buffers(c, LEAN * 0.5))
    change = people.step(c, ration=1.0)

    assert change.left > 0
    assert change.starved == 0


def test_hunger_costs_more_people_than_a_thin_granary_does():
    thin = colony(food=0.0)
    thin.storage.add("food", buffers(thin, LEAN * 0.5))
    starving = colony(food=0.0)
    for _ in range(40):
        people.step(thin, ration=1.0)
        people.step(starving, ration=0.0)

    assert starving.population < thin.population


def test_a_colony_never_quite_empties():
    """Something is always left to build back from -- and an empty colony is a
    division by zero looking for somewhere to happen."""
    c = colony(population=MIN_POPULATION + 0.5, food=0.0)
    for _ in range(4000):
        people.step(c, ration=0.0)

    assert c.population == pytest.approx(MIN_POPULATION)


def test_the_tallies_always_add_up_to_the_population():
    """Born, starved and left are what the viewer and the demo report, so they
    have to account for the population exactly -- including at the floor, where
    a death the floor refused is not a death."""
    for ration, food in ((1.0, None), (0.0, 0.0), (0.4, 0.0)):
        c = colony(food=food)
        start = c.population
        for _ in range(300):
            people.step(c, ration=ration)
        assert c.population == pytest.approx(start + c.growth, abs=1e-9)


# ------------------------------------------------------- what follows from it

def test_eating_is_per_head_and_the_land_is_not():
    """The whole ceiling in one test. Twice the people eat twice as much, and
    do not harvest twice as much, because the fields did not get any bigger."""
    c = colony()
    ate, made = c.consumption["food"], 100.0
    c.production["food"] = made

    c.resize(40.0)

    assert c.consumption["food"] == pytest.approx(2 * ate)
    assert c.production["food"] == pytest.approx(made * 2**LAND_ELASTICITY)
    assert c.production["food"] < 2 * made


def test_a_colony_that_shrinks_feeds_itself_more_easily():
    """The other side of the same coin, and why a starving colony settles at a
    smaller size rather than dying out: fewer mouths against land that did not
    shrink as fast."""
    c = colony()
    c.production["food"] = c.consumption["food"] * 0.8
    before = c.production["food"] / c.consumption["food"]

    c.resize(10.0)

    assert c.production["food"] / c.consumption["food"] > before


def test_resizing_a_day_at_a_time_lands_where_one_big_step_would():
    """Resize is applied as a ratio rather than from a remembered founding
    size, so the daily dribble of births has to multiply out to the same thing
    as one jump. If it drifts, a long run quietly changes the economy."""
    slow, fast = colony(), colony()
    slow.production["food"] = fast.production["food"] = 50.0
    for _ in range(100):
        slow.resize(slow.population * 1.004)
    fast.resize(20.0 * 1.004**100)

    assert slow.population == pytest.approx(fast.population)
    assert slow.production["food"] == pytest.approx(fast.production["food"])
    assert slow.consumption["food"] == pytest.approx(fast.consumption["food"])


def test_a_bigger_colony_wants_a_deeper_granary():
    """Nothing tells the reserve about the population; it follows from
    consumption, which follows from the people. A colony that has grown is
    short of food it would have called surplus last season."""
    c = colony()
    before = c.reserve("food")
    c.resize(30.0)

    assert c.reserve("food") > before
    assert c.shortfall("food") > 0


# -------------------------------------------------------------- who can walk

def enough_for(caravans: float) -> float:
    """The population it takes to crew that many caravans, and a hair over, so
    a test is asking about the rule and not about the last bit of a float."""
    return caravans * CREW / ROAD_SHARE + 0.01


def test_a_colony_crews_more_caravans_as_it_grows():
    assert people.caravans_allowed(enough_for(1)) == 1
    assert people.caravans_allowed(enough_for(2)) == 2
    assert people.caravans_allowed(enough_for(6)) == 6


def test_even_an_emptied_colony_still_sends_one_caravan():
    """Otherwise a colony starved below the crew it takes to fetch food could
    never trade its way back, and the only way out of a bad season would be
    not to have had one."""
    assert people.caravans_allowed(MIN_POPULATION) == 1
    assert people.caravans_allowed(0.0) == 1


def test_guards_come_out_of_the_same_hands_a_second_caravan_would():
    """The choice the coupling exists to create: a colony big enough for two
    carts can send both, or send one and guard it, and not both."""
    two_carts = enough_for(2)

    assert people.caravans_allowed(two_carts) == 2
    assert not people.can_escort(two_carts, caravans_out=2)
    assert people.can_escort(two_carts, caravans_out=1)


def test_a_small_colony_cannot_spare_anyone_to_guard_a_caravan():
    assert not people.can_escort((CREW + GUARDS - 0.1) / ROAD_SHARE, caravans_out=1)
    assert people.can_escort((CREW + GUARDS + 0.1) / ROAD_SHARE, caravans_out=1)


def test_a_colony_that_has_grown_puts_a_second_caravan_on_the_road():
    """End to end, through dispatch: the same world, the same day, and the
    only difference is how many people live in the colony."""
    small = build_simulation(seed=23, settlements=3, wildlife=False)
    big = build_simulation(seed=23, settlements=3, wildlife=False)
    for colony_ in small.colonies:
        colony_.resize(enough_for(1))
    for colony_ in big.colonies:
        colony_.resize(enough_for(4))
    # Read before the run: a colony blown up to four crews is bigger than its
    # own fields can feed, and will have starved some of the way back down by
    # the time forty days are out -- which is the rest of this file's point.
    allowed = (
        max(people.caravans_allowed(c.population) for c in small.colonies),
        min(people.caravans_allowed(c.population) for c in big.colonies),
    )

    small.run(40)
    big.run(40)

    def most_at_once(sim):
        counts: dict[int, int] = {}
        for caravan in sim.caravans:
            counts[caravan.home] = counts.get(caravan.home, 0) + 1
        return max(counts.values(), default=0)

    assert allowed == (1, 4)
    assert most_at_once(small) <= 1
    assert most_at_once(big) > 1


# ------------------------------------------------------------- over a season

def run(seed: int, days: int = DAYS, trade: bool = True, **kwargs):
    sim = build_simulation(seed=seed, stewards=kwargs.pop("stewards", False), **kwargs)
    sim.trade_enabled = trade
    sim.run(days)
    return sim


@pytest.mark.parametrize("seed", SEEDS)
def test_cutting_a_world_off_from_trade_costs_it_people(seed):
    """The point of the feature. Before this, a colony the caravans could not
    reach simply went without, forever, at no cost. Now it loses people.

    The claim is about people lost, not about headcount: a world that trades
    is not always the larger one, because the colony that grew the food and
    sold it has less left to grow on. Nobody dying is the thing trade buys.
    Stewards are off on both sides, so this is the traders' doing and not a
    steward's -- a steward answers a food shortage by moving people into the
    fields, which would save the same colony for another reason entirely.
    """
    traded = run(seed, trade=True)
    alone = run(seed, trade=False)

    assert alone.starved + alone.left > 0, "this world should lose people alone"
    assert traded.starved + traded.left < alone.starved + alone.left


@pytest.mark.parametrize("seed", SEEDS)
def test_nobody_explodes_or_collapses_over_a_season(seed):
    """Calibration, pinned. Under default settings a colony should look
    recognisably like itself after 150 days: noticeably bigger or smaller, not
    a city and not a ruin. If a rate is changed, this is the test that says
    whether the world still works."""
    sim = run(seed, stewards=True)

    for colony_, founded in zip(sim.colonies, [14, 17, 19, 20, 21, 23]):
        assert 0.5 <= colony_.population / max(founded, 1) <= 4.0
    world = sim.population()
    assert 0.8 * 133 <= world <= 2.0 * 152, world


@pytest.mark.parametrize("seed", SEEDS)
def test_a_frozen_world_is_the_world_this_sim_had_before(seed):
    """`population=False` is the control case. Nothing may move: not the
    people, not what they eat, not what the land gives them."""
    sim = build_simulation(seed=seed, population=False)
    founded = [(c.population, dict(c.consumption)) for c in sim.colonies]
    sim.run(DAYS)

    assert sim.born == sim.starved == sim.left == 0.0
    for colony_, (population, consumption) in zip(sim.colonies, founded):
        assert colony_.population == population
        assert colony_.consumption == consumption


def test_population_is_deterministic():
    """People move on stores, and stores move on a seeded world, so two runs
    of a seed must end with the same villages holding the same number of
    people down to the fraction."""
    a, b = run(23, days=90), run(23, days=90)

    assert [c.population for c in a.colonies] == [c.population for c in b.colonies]
    assert (a.born, a.starved, a.left) == (b.born, b.starved, b.left)


def test_a_growing_colony_eats_more_than_it_was_founded_eating():
    """The coupling that gives the economy its stakes, end to end: growth is
    demand. A colony that has gained people wants more food than the world was
    calibrated to give it, and has to get that from somewhere."""
    sim = run(23, stewards=True)
    grown = [c for c in sim.colonies if c.growth >= 1.0]
    assert grown, "no colony grew in this world"

    for colony_ in grown:
        founded = colony_.population - colony_.growth
        assert colony_.consumption["food"] > 0.55 * founded


def test_the_people_are_counted_the_same_way_everywhere():
    """The demo, the viewer and `shrinking_colonies` all report the same
    thing, so they have to agree on what it is."""
    from colonysim.server import state_payload

    sim = run(23, stewards=True)
    payload = state_payload(sim)

    assert payload["people"] == round(sim.population())
    shrinking = set(sim.shrinking_colonies())
    for row, colony_ in zip(payload["colonies"], sim.colonies):
        assert row["people"] == round(colony_.population)
        assert (row["trend"] < 0) == (colony_.name in shrinking)


def test_the_rates_are_slow_enough_to_be_a_season_and_not_a_switch():
    """A guard on the constants themselves. Both of these are per day, and
    both are meant to be things you notice across a season."""
    assert BIRTH_RATE * DAYS < 0.5
    assert HUNGER_RATE * DAYS < 3.0
    assert HUNGER_RATE > BIRTH_RATE, "a colony must fall faster than it climbs"
