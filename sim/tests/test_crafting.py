"""Crafting and hunting: what a colony makes, what it makes it out of, and what
being armed is worth to it."""
from __future__ import annotations

import pytest

from colonysim.crafting import (
    ARMED_FULL,
    CRAFT_LABOUR_PER_CAPITA,
    MATERIAL_SHARE,
    SKILL_START,
    Workshop,
    armed_strength,
    armoury,
    batches_possible,
    order_of_work,
    want,
    work_day,
    work_for,
)
from colonysim.goods import CRAFTED_GOOD_NAMES, GOODS, RAW_GOOD_NAMES
from colonysim.hunting import (
    ARROWS_PER_CAPITA,
    HIDES_PER_ARROW,
    MEAT_PER_ARROW,
    MEAT_PER_ARROW_UNARMED,
    bow_coverage,
    hunt,
    hunters,
    meat_per_arrow,
)
from colonysim.money import SILVER, Purse
from colonysim.recipes import RECIPES, SMITHY, STATIONS, WORK_VALUE, derived_price
from colonysim.simulation import CONSUMPTION_PER_CAPITA, build_simulation
from colonysim.storage import MarketView, Colony
from colonysim.trade import CAPACITY, plan_cargo
from colonysim.wildlife import (
    ARMS_DISCOUNT,
    ESCORT_WAGE,
    Den,
    deterrence,
    escort_cost,
    expected_loss,
    raid,
)
from colonysim.world import Settlement

SEEDS = [1, 7, 23, 99]


def colony(name="A", cid=0, population=20, **stock) -> Colony:
    """A colony with nothing growing and nothing on the shelves but what you
    put there, so what the bench does is the only thing moving.

    Its rack starts where `simulation.build_colony` leaves a real village's:
    on the reserve, so the only thing the workshop is short of is whatever a
    test takes away.
    """
    c = Colony(
        settlement=Settlement(cid, name, 5, 5),
        population=population,
        production={g: 0.0 for g in RAW_GOOD_NAMES},
        consumption={
            good: rate * population for good, rate in CONSUMPTION_PER_CAPITA.items()
        },
        purse=Purse(SILVER, 500.0),
    )
    for good in CRAFTED_GOOD_NAMES:
        c.storage.add(good, c.reserve(good))
    for good, qty in stock.items():
        c.storage.add(good, qty)
    return c


def market(prices=None, surplus=None, shortfall=None, day=0) -> MarketView:
    return MarketView(
        prices={g: GOODS[g].base_price for g in GOODS} | (prices or {}),
        surplus={g: 0.0 for g in GOODS} | (surplus or {}),
        shortfall={g: 0.0 for g in GOODS} | (shortfall or {}),
        day=day,
    )


# ------------------------------------------------------------------ the table

def test_every_recipe_makes_something_the_economy_knows_about():
    """A recipe whose output is not a good would be made and then vanish."""
    for recipe in RECIPES.values():
        assert recipe.output in GOODS
        assert recipe.station in STATIONS
        assert recipe.quantity > 0 and recipe.work > 0
        for material in recipe.inputs:
            assert material in GOODS, f"{recipe.output} is made of nothing"


def test_a_crafted_good_is_worth_its_materials_plus_the_work():
    """Prices are derived so a new recipe cannot be quietly mispriced against
    the rest of the table."""
    for good in CRAFTED_GOOD_NAMES:
        recipe = RECIPES[good]
        materials = sum(qty * GOODS[m].base_price for m, qty in recipe.inputs.items())
        expected = (materials + recipe.work * WORK_VALUE) / recipe.quantity
        assert GOODS[good].base_price == pytest.approx(expected)
        assert GOODS[good].base_price > materials / recipe.quantity


def test_a_raw_good_that_also_has_a_recipe_keeps_the_land_s_price():
    """Tools can be dug for or made. Deriving a second price for them would
    mean the same good was worth two different things."""
    assert "tools" in RECIPES and "tools" in RAW_GOOD_NAMES
    assert GOODS["tools"].base_price == 9.0
    assert derived_price(RECIPES["tools"], lambda g: GOODS[g].base_price) > 0


# --------------------------------------------------------------- the workshop

def test_a_colony_makes_what_it_is_short_of():
    c = colony(wood=400.0, stone=200.0)
    c.storage.remove("arrows", c.storage.get("arrows"))
    assert c.shortfall("arrows") > 0

    made, used = work_day(c)

    assert made["arrows"] > 0
    assert used["wood"] > 0 and used["stone"] > 0
    assert c.storage.get("arrows") == pytest.approx(made["arrows"])


def test_crafting_never_eats_into_the_reserve():
    """The one thing that must not happen: a colony whittling its own buffer
    into arrows. Every recipe draws on surplus, exactly as barter does."""
    c = colony(wood=400.0, stone=200.0)
    c.storage.remove("arrows", c.storage.get("arrows"))
    before = {good: c.storage.get(good) for good in RAW_GOOD_NAMES}

    for _ in range(60):
        work_day(c)

    for good in RAW_GOOD_NAMES:
        assert c.storage.get(good) >= min(before[good], c.reserve(good)) - 1e-9


def test_a_bench_takes_only_a_share_of_the_pile_in_a_day():
    """Surplus is a stock, not a daily rate. A workshop that ground the whole
    pile in a day would leave nothing to trade with or build with."""
    c = colony(wood=400.0, stone=200.0)
    c.storage.remove("arrows", c.storage.get("arrows"))
    spare = c.surplus("wood")

    work_day(c)

    assert c.surplus("wood") > spare * (1.0 - MATERIAL_SHARE) - 1e-9


def test_a_colony_with_no_materials_makes_nothing():
    c = colony()
    c.storage.remove("arrows", c.storage.get("arrows"))
    assert batches_possible(c, RECIPES["arrows"]) == 0.0
    assert work_day(c) == ({}, {})


def test_crafting_turns_materials_into_goods_and_nothing_else():
    """Conservation at the bench: the wood that went in is gone from the
    shelves, and the arrows that came out are on them."""
    c = colony(wood=400.0, stone=200.0)
    c.storage.remove("arrows", c.storage.get("arrows"))
    before = {good: c.storage.get(good) for good in GOODS}

    made, used = work_day(c)

    for good in GOODS:
        expected = before[good] + made.get(good, 0.0) - used.get(good, 0.0)
        assert c.storage.get(good) == pytest.approx(expected, abs=1e-9), good


def test_a_workshop_will_not_make_for_demand_it_has_already_met():
    """A village with ten bows in the rack and a neighbour wanting two does not
    need an eleventh. Without this a durable good is made forever."""
    c = colony(wood=400.0, cloth=200.0, bow=60.0)
    c.known[1] = market(prices={"bow": 99.0}, shortfall={"bow": 2.0})
    assert c.surplus("bow") > 2.0
    assert want(c, "bow") == 0.0

    made, _ = work_day(c)
    assert "bow" not in made


def test_a_colony_makes_for_a_neighbour_that_is_short_and_paying():
    """Crafting for export, which is the whole of what makes a crafted good a
    trade good rather than a private stockpile."""
    keen = colony(wood=600.0, cloth=300.0)
    keen.workshop.skill = 1.0
    quiet = colony(wood=600.0, cloth=300.0)
    quiet.workshop.skill = 1.0
    keen.known[1] = market(prices={"bow": 99.0}, shortfall={"bow": 40.0})

    for _ in range(10):
        work_day(keen)
        work_day(quiet)

    assert keen.storage.get("bow") > quiet.storage.get("bow")


def test_nobody_makes_for_a_market_that_is_cheaper_than_home():
    """There is no trip in hauling a bow somewhere it is worth less."""
    c = colony(wood=600.0, cloth=300.0, bow=10.0)
    c.known[1] = market(prices={"bow": 0.01}, shortfall={"bow": 80.0})
    assert want(c, "bow") == 0.0


def test_a_poor_hand_takes_longer_and_practice_shortens_it():
    recipe = RECIPES["arrows"]
    assert work_for(recipe, 0.0) > work_for(recipe, 1.0)
    assert work_for(recipe, 1.0) == pytest.approx(recipe.work)

    shop = Workshop()
    shop.practise(20.0)
    assert shop.skill > SKILL_START


def test_a_fresh_workshop_cannot_make_a_bow_until_it_has_practised():
    """The skill floor is what gives a workshop somewhere to get to."""
    shop = Workshop()
    assert not shop.can_make(RECIPES["bow"])
    assert shop.can_make(RECIPES["club"])

    shop.practise(200.0)
    assert shop.can_make(RECIPES["bow"])


def test_the_bench_works_on_what_earns_most_per_day_first():
    c = colony(wood=600.0, stone=300.0, cloth=300.0)
    c.workshop.skill = 1.0
    for good in ("arrows", "club", "spear", "bow"):
        c.storage.remove(good, c.storage.get(good))

    order = order_of_work(c)
    assert order, "nothing at all was worth making"
    earnings = [
        c.price(r.output) * r.quantity / work_for(r, c.workshop.skill) for r in order
    ]
    assert earnings == sorted(earnings, reverse=True)


def test_a_steward_that_has_switched_a_good_off_stops_it_being_made():
    c = colony(wood=400.0, stone=200.0)
    c.storage.remove("arrows", c.storage.get("arrows"))
    c.policy.set_craft("arrows", 0.0)

    made, _ = work_day(c)
    assert "arrows" not in made


# ----------------------------------------------------------------- the smithy

def test_no_knife_without_a_smithy():
    c = colony(wood=400.0, stone=400.0)
    c.workshop.skill = 1.0
    c.storage.remove("knife", c.storage.get("knife"))

    made, _ = work_day(c)
    assert "knife" not in made
    assert not c.workshop.can_make(RECIPES["knife"])


def test_a_smithy_is_gathered_for_then_built_then_used():
    c = colony(wood=400.0, stone=400.0)
    c.workshop.skill = 1.0
    c.storage.remove("knife", c.storage.get("knife"))
    c.workshop.raising = SMITHY.name
    assert c.workshop.owed() == SMITHY.cost

    stone_before = c.storage.get("stone")
    for _ in range(80):
        work_day(c)
        if SMITHY.name in c.workshop.stations:
            break

    assert SMITHY.name in c.workshop.stations
    assert c.storage.get("stone") < stone_before
    assert not c.workshop.raising and c.workshop.owed() == {}

    made, _ = work_day(c)
    assert made.get("knife", 0.0) > 0


def test_a_colony_with_nothing_to_spare_waits_and_keeps_working():
    """Commissioning a bench it cannot afford must not stall the workshop."""
    c = colony(wood=400.0, stone=0.0)
    c.storage.remove("club", c.storage.get("club"))
    c.workshop.raising = SMITHY.name

    made, _ = work_day(c)

    assert SMITHY.name not in c.workshop.stations
    assert c.workshop.owed()["stone"] == SMITHY.cost["stone"]
    assert made.get("club", 0.0) > 0, "the bench sat idle waiting for stone"


def test_a_workshop_says_what_it_is_doing():
    """The line the viewer and a steward's brief both show."""
    c = colony(wood=400.0, stone=200.0)
    c.storage.remove("arrows", c.storage.get("arrows"))
    work_day(c)
    assert "crafting spot" in c.workshop.describe()
    assert "arrows" in c.workshop.describe()


# ---------------------------------------------------------------- the hunting

def test_arrows_spent_come_back_as_meat_and_hides():
    c = colony(bow=20.0)
    bag = hunt(c, 10.0)

    assert bag["food"] == pytest.approx(10.0 * MEAT_PER_ARROW)
    assert bag["cloth"] == pytest.approx(10.0 * HIDES_PER_ARROW)
    assert c.storage.get("food") == pytest.approx(bag["food"])


def test_a_colony_with_no_arrows_brings_nothing_home():
    assert hunt(colony(bow=20.0), 0.0) == {}


def test_bows_are_what_turn_a_day_in_the_woods_into_food():
    """The reason a colony wants a fletcher and a bowyer at all."""
    armed = colony(bow=40.0)
    barehanded = colony()
    barehanded.storage.remove("bow", barehanded.storage.get("bow"))

    assert bow_coverage(armed) == 1.0
    assert bow_coverage(barehanded) == 0.0
    assert meat_per_arrow(armed) == pytest.approx(MEAT_PER_ARROW)
    assert meat_per_arrow(barehanded) == pytest.approx(MEAT_PER_ARROW_UNARMED)
    assert hunt(armed, 10.0)["food"] > hunt(barehanded, 10.0)["food"]


def test_half_the_party_with_bows_hunts_between_the_two():
    c = colony()
    c.storage.remove("bow", c.storage.get("bow"))
    c.storage.add("bow", hunters(c) / 2.0)
    assert bow_coverage(c) == pytest.approx(0.5)
    assert MEAT_PER_ARROW_UNARMED < meat_per_arrow(c) < MEAT_PER_ARROW


def test_hunting_is_what_arrows_are_consumed_for():
    """The consumption rate and the hunt are the same number, so a colony's
    arrow demand is exactly what its hunters shoot."""
    assert CONSUMPTION_PER_CAPITA["arrows"] == ARROWS_PER_CAPITA


# ------------------------------------------------------------------- the arms

def test_being_armed_is_measured_off_the_armoury():
    empty = colony()
    for good in CRAFTED_GOOD_NAMES:
        empty.storage.remove(good, empty.storage.get(good))
    assert armed_strength(empty) == 0.0

    few = colony()
    for good in CRAFTED_GOOD_NAMES:
        few.storage.remove(good, few.storage.get(good))
    few.storage.add("club", 2.0)
    assert 0.0 < armed_strength(few) < 1.0

    enough = colony()
    for good in CRAFTED_GOOD_NAMES:
        enough.storage.remove(good, enough.storage.get(good))
    enough.storage.add("bow", enough.population * ARMED_FULL)
    assert armed_strength(enough) == pytest.approx(1.0)

    full = colony(bow=200.0)
    assert armed_strength(full) == 1.0, "more weapons than people is still armed"
    assert armoury(full)["bow"] == full.storage.get("bow")


def test_a_bow_counts_for_more_than_a_club():
    bows = colony()
    clubs = colony()
    for c in (bows, clubs):
        for good in CRAFTED_GOOD_NAMES:
            c.storage.remove(good, c.storage.get(good))
    bows.storage.add("bow", 3.0)
    clubs.storage.add("club", 3.0)
    assert armed_strength(bows) > armed_strength(clubs)


def test_armed_people_make_guards_cheaper_and_animals_warier():
    days = 6.0
    assert escort_cost(days, arms=0.0) == pytest.approx(ESCORT_WAGE * days)
    assert escort_cost(days, arms=1.0) == pytest.approx(
        ESCORT_WAGE * days * (1.0 - ARMS_DISCOUNT)
    )
    assert deterrence(False, arms=1.0) > deterrence(False, arms=0.0)
    assert deterrence(True, arms=1.0) > deterrence(True, arms=0.0)
    assert expected_loss(0.5, 100.0, arms=1.0) < expected_loss(0.5, 100.0)


def test_weapons_do_not_change_a_world_that_never_had_any():
    """Every default is the old number, so the wildlife layer as it was is the
    control case for what arming a colony does."""
    assert deterrence(False, 0.0) == 0.0
    assert escort_cost(4.0) == escort_cost(4.0, arms=0.0)
    assert expected_loss(0.3, 50.0) == expected_loss(0.3, 50.0, arms=0.0)


def test_an_armed_caravan_is_likelier_to_drive_the_animals_off():
    class Rolls:
        def __init__(self, *values: float) -> None:
            self.values = list(values)

        def random(self) -> float:
            return self.values.pop(0) if self.values else 0.5

    # A roll that a barehanded caravan fails and an armed one passes.
    den = Den(0, "wolves", 10, 10)
    bare = raid(Rolls(0.6), den, {"food": 40.0}, False, day=1, arms=0.0)
    armed = raid(Rolls(0.6), Den(0, "wolves", 10, 10), {"food": 40.0}, False, 1, 1.0)

    assert bare.outcome != "drove off"
    assert armed.outcome == "drove off"


def test_a_caravan_carries_its_colony_s_arms_onto_the_road():
    sim = build_simulation(seed=23, settlements=3)
    while not sim.caravans:
        sim.step_day()
    for caravan in sim.caravans:
        assert caravan.arms == pytest.approx(
            armed_strength(sim.colonies[caravan.home])
        )


# ---------------------------------------------------------------- trade in it

def test_a_caravan_will_load_crafted_goods():
    """Ryan's ask: what the benches make has to move. Nothing in the trade code
    knows crafting exists -- a bow is cargo because it is a good."""
    seller = colony(bow=40.0)
    abroad = market(prices={"bow": 99.0}, shortfall={"bow": 10.0})

    cargo = plan_cargo(seller, abroad, CAPACITY)
    assert cargo.get("bow", 0.0) > 0


def test_crafted_goods_actually_change_hands_on_a_running_world():
    moved = 0
    for seed in SEEDS:
        sim = build_simulation(seed=seed)
        sim.run(150)
        for line in sim.log:
            if any(good in line for good in CRAFTED_GOOD_NAMES):
                moved += 1
    assert moved > 0, "no caravan ever bought or sold anything crafted"


# ----------------------------------------------------------------- the world

@pytest.mark.parametrize("seed", SEEDS)
def test_a_running_world_makes_things_and_hunts(seed):
    sim = build_simulation(seed=seed)
    sim.run(150)

    assert sum(sim.crafted.values()) > 0, "nobody made anything all year"
    assert sim.crafted.get("arrows", 0.0) > 0, "nobody fletched an arrow"
    assert sim.hunted.get("food", 0.0) > 0, "nobody hunted"
    assert sim.hunted.get("cloth", 0.0) > 0, "no hides came home"
    # Hunting is a supplement, not a second farm.
    assert sim.hunted["food"] < 0.25 * sim.produced["food"]


def test_somebody_builds_a_smithy_when_it_wants_what_one_makes():
    built = [
        colony.name
        for seed in SEEDS
        for colony in _run(seed).colonies
        if "smithy" in colony.workshop.stations
    ]
    assert built, "no colony ever built a bench"


def _run(seed: int):
    sim = build_simulation(seed=seed)
    sim.run(150)
    return sim


@pytest.mark.parametrize("seed", SEEDS)
def test_the_benches_and_the_hunt_create_nothing_from_nothing(seed):
    """Conservation again, over the crafted goods this time: every arrow on a
    shelf was made out of wood and stone that is no longer on one."""
    sim = build_simulation(seed=seed)
    start = sim.goods_in_world()
    sim.run(120)
    end = sim.goods_in_world()

    for good in CRAFTED_GOOD_NAMES:
        expected = (
            start[good]
            + sim.produced.get(good, 0.0)
            - sim.consumed.get(good, 0.0)
            - sim.lost.get(good, 0.0)
        )
        assert end[good] == pytest.approx(expected, abs=1e-6), good


def test_a_workshop_run_world_still_replays_exactly():
    """Nothing in crafting or hunting rolls a die."""
    a, b = _run(23), _run(23)
    assert [c.storage.stock for c in a.colonies] == [c.storage.stock for c in b.colonies]
    assert [c.workshop.skill for c in a.colonies] == [
        c.workshop.skill for c in b.colonies
    ]
    assert a.crafted == b.crafted and a.hunted == b.hunted


def test_the_labour_a_colony_gives_its_bench_is_its_own():
    """A workshop's day comes out of the population, so a bigger village makes
    more. Nothing here moves people out of the fields."""
    small = colony(population=10, wood=600.0, stone=300.0)
    large = colony(population=40, wood=600.0, stone=300.0)
    for c in (small, large):
        c.storage.remove("arrows", c.storage.get("arrows"))

    made_small, _ = work_day(small)
    made_large, _ = work_day(large)

    assert made_large["arrows"] > made_small["arrows"]
    assert large.population * CRAFT_LABOUR_PER_CAPITA > 0
