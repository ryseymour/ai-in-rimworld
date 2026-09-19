"""Hunting: where the game is, what a party brings home, and what it risks."""
from __future__ import annotations

import random

import pytest

from colonysim.crafting import armed_strength
from colonysim.hunting import (
    ARROWS_PER_CAPITA,
    SEASON_GAME,
    BOAR,
    BOWLESS_TAKE,
    DEER,
    GAME,
    HUNTER_SHARE,
    HUNT_RANGE,
    MAX_ABUNDANCE,
    PREDATOR_TOLL,
    THINNING,
    Herd,
    Herds,
    HuntingGround,
    bow_coverage,
    field_hands,
    hunt,
    hunters,
    meat_per_arrow,
    open_country,
    party_share,
    populate,
)
from colonysim.money import SILVER, Purse
from colonysim.simulation import CONSUMPTION_PER_CAPITA, build_simulation
from colonysim.storage import MAX_HUNT, Colony, Storage
from colonysim.wildlife import Den, Wilds
from colonysim.world import Settlement, generate_world

SEEDS = [1, 7, 23, 99]


class Rolls:
    """A stand-in for `random.Random` handing back the rolls you name, so one
    day's hunting can be pinned to one outcome."""

    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.5


def colony(name="A", cid=0, population=20, x=5, y=5, **stock) -> Colony:
    """A colony with nothing growing and nothing on the shelves but what you
    put there, so the only thing moving is the hunt."""
    c = Colony(
        settlement=Settlement(cid, name, x, y),
        population=population,
        production={},
        consumption={"food": 0.55 * population, "arrows": ARROWS_PER_CAPITA * population},
        storage=Storage(),
        purse=Purse(SILVER, 0.0),
    )
    for good, qty in stock.items():
        c.storage.add(good, qty)
    return c


def herds(*placed: tuple[str, int, int]) -> Herds:
    return Herds(tuple(Herd(i, s, x, y) for i, (s, x, y) in enumerate(placed)))


def ground(abundance=1.0, mix=None, danger=0.0, predator="", ids=()) -> HuntingGround:
    return HuntingGround(
        abundance=abundance,
        mix=mix or {DEER.name: 1.0},
        danger=danger,
        predator=predator,
        herds=tuple(ids),
    )


# ------------------------------------------------------------- where game is

@pytest.mark.parametrize("seed", SEEDS)
def test_herds_live_on_ground_that_suits_them(seed):
    world = generate_world(90, 45, 6, seed)
    found = populate(world, seed)

    assert found.herds, "no game anywhere on the map"
    for herd in found.herds:
        kind = world.terrain.kind(herd.x, herd.y)
        assert herd.kind.habitat.get(kind, 0.0) > 0.0, f"{herd.species} in {kind}"


@pytest.mark.parametrize("seed", SEEDS)
def test_game_does_not_keep_away_from_villages_the_way_predators_do(seed):
    """The one place the herds and the dens differ, and the reason a colony has
    any hunting at all: deer graze the edge of a field."""
    world = generate_world(90, 45, 6, seed)
    found = populate(world, seed)
    close = [
        herd
        for herd in found.herds
        for s in world.settlements
        if abs(herd.x - s.x) <= HUNT_RANGE and abs(herd.y - s.y) <= HUNT_RANGE
    ]
    assert close, "every herd on the map is out of reach of every village"


def test_the_game_is_deterministic_and_seed_dependent():
    world = generate_world(60, 30, 4, 11)
    again = populate(world, 11)
    assert [h.pos for h in populate(world, 11).herds] == [h.pos for h in again.herds]
    assert [h.pos for h in populate(world, 12).herds] != [h.pos for h in again.herds]


def test_ground_is_better_where_there_is_more_game():
    one = herds((DEER.name, 5, 5))
    three = herds((DEER.name, 5, 5), (DEER.name, 6, 6), (BOAR.name, 4, 4))
    assert three.ground(5, 5).abundance > one.ground(5, 5).abundance


def test_ground_is_worse_where_the_herds_are_thin():
    thin = herds((DEER.name, 5, 5))
    thin.herds[0].strength = 0.2
    full = herds((DEER.name, 5, 5))
    assert thin.ground(5, 5).abundance < full.ground(5, 5).abundance


def test_a_colony_with_nothing_in_reach_has_no_hunting():
    far = herds((DEER.name, 60, 60))
    assert far.ground(5, 5).empty
    assert far.ground(5, 5).abundance == 0.0


def test_the_best_country_is_still_only_so_good():
    """A colony cannot sit on a wood so rich that the fields stop mattering."""
    crowded = herds(*[(DEER.name, 5 + i % 3, 5 + i // 3) for i in range(20)])
    assert crowded.ground(5, 5).abundance == MAX_ABUNDANCE


def test_what_is_out_there_is_what_comes_home():
    deer_country = herds((DEER.name, 5, 5))
    boar_country = herds((BOAR.name, 5, 5))
    assert deer_country.ground(5, 5).mix == {DEER.name: 1.0}
    assert boar_country.ground(5, 5).mix == {BOAR.name: 1.0}

    both = herds((DEER.name, 5, 5), (BOAR.name, 5, 5))
    mix = both.ground(5, 5).mix
    assert mix[DEER.name] == pytest.approx(0.5)
    assert mix[BOAR.name] == pytest.approx(0.5)


# ------------------------------------------------------------ what comes home

def test_arrows_spent_come_back_as_meat_and_hides():
    c = colony(bow=20.0)
    party = hunt(c, 10.0, ground())

    assert party.taken[DEER.name] == pytest.approx(10.0 / DEER.arrows_each)
    assert party.bag["food"] == pytest.approx(
        10.0 * DEER.meat / DEER.arrows_each
    )
    assert party.bag["cloth"] == pytest.approx(
        10.0 * DEER.hides / DEER.arrows_each
    )
    assert c.storage.get("food") == pytest.approx(party.bag["food"])
    assert c.storage.get("cloth") == pytest.approx(party.bag["cloth"])


def test_a_colony_on_its_own_hunts_ordinary_country():
    """A colony with nobody keeping a map hunts `open_country`: middling
    ground with deer and boar on it, which is what the sim did before the
    herds were on the terrain."""
    assert open_country().abundance == 1.0
    assert hunt(colony(bow=40.0), 10.0).bag["food"] == pytest.approx(
        hunt(colony(bow=40.0), 10.0, open_country()).bag["food"]
    )


def test_a_colony_with_no_arrows_brings_nothing_home():
    assert hunt(colony(bow=20.0), 0.0, ground()).bag == {}


def test_a_colony_with_nowhere_to_hunt_brings_nothing_home():
    empty = HuntingGround(abundance=0.0, mix={})
    assert hunt(colony(bow=20.0), 10.0, empty).bag == {}


def test_bows_are_what_turn_a_day_in_the_woods_into_food():
    """The reason a colony wants a fletcher and a bowyer at all."""
    armed = colony(bow=40.0)
    barehanded = colony()

    assert bow_coverage(armed) == 1.0
    assert bow_coverage(barehanded) == 0.0
    assert meat_per_arrow(barehanded) == pytest.approx(
        BOWLESS_TAKE * meat_per_arrow(armed)
    )
    assert hunt(armed, 10.0, ground()).bag["food"] > hunt(
        barehanded, 10.0, ground()
    ).bag["food"]


def test_half_the_party_with_bows_hunts_between_the_two():
    c = colony()
    c.storage.add("bow", hunters(c) / 2.0)
    assert bow_coverage(c) == pytest.approx(0.5)
    barehanded = meat_per_arrow(colony())
    armed = meat_per_arrow(colony(bow=40.0))
    assert barehanded < meat_per_arrow(c) < armed


def test_better_country_feeds_the_same_arrows_further():
    c = colony(bow=40.0)
    poor = hunt(colony(bow=40.0), 10.0, ground(abundance=0.4)).bag["food"]
    rich = hunt(c, 10.0, ground(abundance=1.3)).bag["food"]
    assert rich > poor


def test_a_boar_is_more_meat_and_more_arrows_than_a_deer():
    boar = hunt(colony(bow=40.0), 12.0, ground(mix={BOAR.name: 1.0}))
    deer = hunt(colony(bow=40.0), 12.0, ground(mix={DEER.name: 1.0}))
    assert boar.taken[BOAR.name] < deer.taken[DEER.name]
    assert BOAR.meat > DEER.meat


def test_hunting_is_what_arrows_are_consumed_for():
    """The consumption rate and the hunt are the same number, so a colony's
    arrow demand is exactly what its hunters shoot."""
    assert CONSUMPTION_PER_CAPITA["arrows"] == ARROWS_PER_CAPITA


# ---------------------------------------------------------------- the party

def test_a_bigger_village_sends_more_people_out():
    assert hunters(colony(population=40)) > hunters(colony(population=10))
    assert hunters(colony(population=20)) == pytest.approx(20 * HUNTER_SHARE)


def test_sending_more_people_brings_more_home_and_less_each():
    c = colony(bow=200.0)
    ordinary = hunt(colony(bow=200.0), 10.0, ground()).bag["food"]
    c.policy.set_hunt(2.0)
    harder = hunt(c, 10.0, ground()).bag["food"]

    assert harder > ordinary
    # Twice the party is not twice the meat: more hands help, less each time.
    assert harder < 2.0 * ordinary


def test_hands_in_the_woods_are_hands_off_the_land():
    """The whole cost of the hunting dial, and the reason a farm village never
    leans on it."""
    c = colony()
    assert field_hands(c) == pytest.approx(1.0)

    c.policy.set_hunt(MAX_HUNT)
    assert field_hands(c) < 1.0
    assert field_hands(c) == pytest.approx(
        1.0 - (party_share(c) - HUNTER_SHARE)
    )


def test_a_colony_that_hunts_harder_harvests_less():
    farm = Colony(
        settlement=Settlement(0, "A", 5, 5),
        population=20,
        production={"food": 10.0},
        consumption={"food": 10.0},
        storage=Storage(),
    )
    before = farm.output("food")
    farm.policy.set_hunt(MAX_HUNT)
    assert farm.output("food") < before


# ------------------------------------------------------------- thinning out

def test_hunting_thins_the_herd_it_was_taken_from():
    country = herds((DEER.name, 5, 5))
    spot = country.ground(5, 5)
    country.thin(spot, {DEER.name: 2.0})
    assert country.herds[0].strength == pytest.approx(1.0 - 2.0 * THINNING)


def test_the_take_is_spread_over_every_herd_the_party_could_reach():
    """Which is why a colony with one herd in reach empties it and a colony
    with five hunts the same number of animals for years."""
    alone = herds((DEER.name, 5, 5))
    several = herds((DEER.name, 5, 5), (DEER.name, 6, 5), (DEER.name, 5, 6))
    alone.thin(alone.ground(5, 5), {DEER.name: 3.0})
    several.thin(several.ground(5, 5), {DEER.name: 3.0})

    assert alone.herds[0].strength < several.herds[0].strength


def test_a_herd_is_only_thinned_by_its_own_kind_being_shot():
    country = herds((DEER.name, 5, 5), (BOAR.name, 5, 5))
    country.thin(country.ground(5, 5), {DEER.name: 2.0})
    assert country.herds[0].strength < 1.0
    assert country.herds[1].strength == 1.0


def test_a_herd_left_alone_comes_back():
    country = herds((DEER.name, 5, 5))
    country.herds[0].strength = 0.2
    for _ in range(200):
        country.graze_day()
    assert country.herds[0].strength > 0.9


def test_a_herd_never_grows_past_full_and_never_goes_below_nothing():
    country = herds((DEER.name, 5, 5))
    for _ in range(50):
        country.graze_day()
    assert country.herds[0].strength == 1.0

    country.thin(country.ground(5, 5), {DEER.name: 500.0})
    assert country.herds[0].strength == 0.0


def test_a_ground_hunted_flat_out_settles_thinner_than_one_left_alone():
    """The ceiling on hunting: a party that takes more than the ground grows
    back walks further every season for less."""
    worked = herds((DEER.name, 5, 5))
    for _ in range(300):
        worked.thin(worked.ground(5, 5), {DEER.name: 0.3})
        worked.graze_day()

    quiet = herds((DEER.name, 5, 5))
    for _ in range(300):
        quiet.graze_day()

    assert worked.herds[0].strength < 0.5 * quiet.herds[0].strength


# ------------------------------------------------------------------ the year

def test_the_four_seasons_of_hunting_average_to_an_ordinary_year():
    """The same bargain the land gets in `weather.py`: a year's hunting is a
    year's hunting, and the seasons only decide when it happens."""
    assert sum(SEASON_GAME.values()) / len(SEASON_GAME) == pytest.approx(1.0)
    assert set(SEASON_GAME) == {"spring", "summer", "autumn", "winter"}


def test_autumn_is_the_hunt_of_the_year_and_spring_is_lean():
    country = herds((DEER.name, 5, 5), (BOAR.name, 6, 5))
    autumn = country.ground(5, 5, None, "autumn").abundance
    spring = country.ground(5, 5, None, "spring").abundance
    plain = country.ground(5, 5).abundance

    assert spring < plain < autumn


def test_a_season_finds_more_of_the_herd_rather_than_making_more_of_it():
    """Shoot a wood out in autumn and it is still shot out come spring."""
    country = herds((DEER.name, 5, 5))
    country.thin(country.ground(5, 5), {DEER.name: 2.0})
    thinned = country.herds[0].strength

    country.ground(5, 5, None, "autumn")
    assert country.herds[0].strength == thinned


def test_a_world_with_no_calendar_hunts_the_same_woods_all_year():
    """The control case: `weather=False` is a year with no seasons in it, so
    the only thing that moves a colony's ground is the hunting it has done."""
    tame = build_simulation(seed=7, weather=False)
    assert tame.climate is None
    mean = _ground_by_season(tame)
    # Spring comes first and autumn third, so with no season on the hunting the
    # ground can only have gone down between them.
    assert mean["autumn"] <= mean["spring"]


@pytest.mark.parametrize("seed", SEEDS)
def test_a_year_of_hunting_has_a_shape_to_it(seed):
    """What a colony sees in its own woods over a year, which is what its
    steward decides how many people to send on."""
    mean = _ground_by_season(build_simulation(seed=seed))
    assert mean["autumn"] > mean["spring"]


def _ground_by_season(sim, days: int = 180) -> dict[str, float]:
    """Mean hunting ground across the colonies, by season, over a run."""
    seen: dict[str, list[float]] = {}
    for _ in range(days):
        sim.step_day()
        ground = [c.hunting_ground for c in sim.colonies]
        seen.setdefault(sim.season.name, []).append(sum(ground) / len(ground))
    return {season: sum(v) / len(v) for season, v in seen.items()}


# ------------------------------------------------------------------ the wild

def test_the_wild_reaches_a_hunting_party_where_it_reaches_no_caravan():
    """Hunters are off the road by definition, so nothing divides the hazard
    down and there is nobody to hire."""
    wilds = Wilds((Den(0, "wolves", 5, 5),))
    country = herds((DEER.name, 5, 5))
    spot = country.ground(5, 5, wilds)

    assert spot.danger > wilds.danger_at(5, 5)
    assert spot.predator == "wolves"


def test_country_with_nothing_in_it_is_safe_to_hunt():
    country = herds((DEER.name, 5, 5))
    assert country.ground(5, 5, Wilds(())).danger == 0.0
    assert country.ground(5, 5).danger == 0.0


def test_wolves_take_most_of_what_the_party_was_carrying():
    c = colony(bow=40.0)
    quiet = hunt(colony(bow=40.0), 10.0, ground())
    raided = hunt(c, 10.0, ground(danger=1.0, predator="wolves"), Rolls(0.0, 0.99))

    assert raided.mishap == "wolves"
    assert raided.bag["food"] == pytest.approx(
        quiet.bag["food"] * (1.0 - PREDATOR_TOLL)
    )
    # What the wolves took never reached a shelf, so it was never in the world.
    assert c.storage.get("food") == pytest.approx(raided.bag["food"])


def test_a_party_can_lose_somebody():
    c = colony(bow=40.0)
    mauled = hunt(c, 10.0, ground(danger=1.0, predator="bears"), Rolls(0.0, 0.0))
    assert mauled.hurt == 1.0
    assert "did not come home" in mauled.describe()


def test_arms_are_what_a_party_has_instead_of_guards():
    """A colony that armed its people meets the wild less often -- the same
    loop the caravans already run on, with nobody to hire at the end of it."""
    armed = colony(population=20, bow=40.0, spear=40.0)
    lightly = colony(population=20, bow=2.0)
    assert armed_strength(armed) > armed_strength(lightly)

    dangerous = ground(danger=0.5, predator="wolves")
    met = sum(
        1
        for seed in range(200)
        if hunt(armed, 10.0, dangerous, random.Random(seed)).mishap
    )
    met_lightly = sum(
        1
        for seed in range(200)
        if hunt(lightly, 10.0, dangerous, random.Random(seed)).mishap
    )
    assert met < met_lightly


def test_a_boar_can_turn_on_the_party_with_nothing_else_about():
    c = colony(bow=40.0)
    gored = hunt(c, 40.0, ground(mix={BOAR.name: 1.0}), Rolls(0.0, 0.0))
    assert gored.mishap == "boar"
    assert "a boar turned on them" in gored.describe()


def test_nothing_is_rolled_without_a_die():
    """A hunt is a rate; only the wild is a die. Without an rng the party
    always comes home whole, which is what keeps the unit tests above about
    arithmetic rather than about luck."""
    party = hunt(colony(bow=40.0), 10.0, ground(danger=1.0, predator="bears"))
    assert party.mishap == ""
    assert party.hurt == 0.0


# --------------------------------------------------------------- the stewards

def test_a_hungry_colony_with_game_and_arrows_sends_more_people_out():
    sim = build_simulation(seed=3)
    steward = sim.stewards[0]
    colony_ = steward.colony
    colony_.hunting_ground = 1.2
    before = colony_.policy.hunt_share()
    for _ in range(70):
        # Restated each day: a steward's memory drifts back towards what its
        # shelves actually say, and this is a test about one situation.
        steward.memory = {"food": 0.4, "arrows": 1.0}
        steward.review(sim.network_view(colony_.id))
    assert colony_.policy.hunt_share() > before


def test_a_colony_with_an_empty_quiver_mostly_stays_in_the_fields():
    """Hunger alone is not a reason to stand in the trees: without arrows to
    shoot, a hungry village puts its hands back on the land."""
    assert _hungry_dial(quiver=0.0) < _hungry_dial(quiver=1.0)
    assert _hungry_dial(quiver=0.0) < 1.1


def _hungry_dial(quiver: float) -> float:
    sim = build_simulation(seed=3)
    steward = sim.stewards[0]
    steward.colony.hunting_ground = 1.2
    for _ in range(70):
        steward.memory = {"food": 0.4, "arrows": quiver}
        steward.review(sim.network_view(steward.colony.id))
    return steward.colony.policy.hunt_share()


def test_a_well_fed_colony_pulls_its_hunters_back_to_the_land():
    sim = build_simulation(seed=3)
    steward = sim.stewards[0]
    colony_ = steward.colony
    colony_.hunting_ground = 1.2
    for _ in range(70):
        steward.memory = {"food": 1.9, "arrows": 1.0}
        steward.review(sim.network_view(colony_.id))
    assert colony_.policy.hunt_share() < 1.0


# ----------------------------------------------------------------- the world

@pytest.mark.parametrize("seed", SEEDS)
def test_a_running_world_hunts_and_the_hunting_shows_in_the_ledger(seed):
    sim = build_simulation(seed=seed)
    sim.run(150)

    assert sim.hunted.get("food", 0.0) > 0, "nobody hunted"
    assert sim.hunted.get("cloth", 0.0) > 0, "no hides came home"
    assert sum(sim.game_taken.values()) > 0, "no animals were taken"
    assert set(sim.game_taken) <= set(GAME)
    # A supplement, not a second farm.
    assert sim.hunted["food"] < 0.25 * sim.produced["food"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_hunting_is_the_colonys_own_ground(seed):
    """Two villages on the same map hunt differently because the country
    around them is different, which is the whole reason the herds are on the
    map rather than on the colony."""
    sim = build_simulation(seed=seed)
    sim.run(30)
    grounds = [c.hunting_ground for c in sim.colonies]
    assert max(grounds) - min(grounds) > 0.1


def test_a_hunted_world_still_replays_exactly():
    a, b = build_simulation(seed=23), build_simulation(seed=23)
    a.run(60)
    b.run(60)
    assert a.hunted == b.hunted
    assert a.game_taken == b.game_taken
    assert [h.strength for h in a.herds.herds] == [h.strength for h in b.herds.herds]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_herds_are_thinner_where_the_hunting_has_been(seed):
    sim = build_simulation(seed=seed)
    sim.run(150)
    worked = [
        herd.strength
        for herd in sim.herds.herds
        if any(
            abs(herd.x - c.settlement.x) <= HUNT_RANGE
            and abs(herd.y - c.settlement.y) <= HUNT_RANGE
            for c in sim.colonies
        )
    ]
    assert worked, "no colony had anything in reach all year"
    assert min(worked) < 1.0, "a year of hunting cost the game nothing"


@pytest.mark.parametrize("seed", SEEDS)
def test_an_empty_wood_is_a_world_that_hunts_less(seed):
    """The control case for the herds: the same world with nothing living in
    it in particular hunts ordinary country everywhere."""
    wild = build_simulation(seed=seed)
    wild.run(120)
    bare = build_simulation(seed=seed, game=False)
    bare.run(120)

    assert bare.hunted["food"] > 0
    assert bare.game_taken
    assert wild.hunted["food"] != bare.hunted["food"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_hunt_creates_nothing_from_nothing(seed):
    """Meat and hides are produced like anything else, and what a predator took
    off the party never reached a shelf to be counted."""
    sim = build_simulation(seed=seed)
    start = sim.goods_in_world()
    sim.run(120)
    end = sim.goods_in_world()

    for good in ("food", "cloth"):
        expected = (
            start[good]
            + sim.produced.get(good, 0.0)
            - sim.consumed.get(good, 0.0)
            - sim.lost.get(good, 0.0)
        )
        assert end[good] == pytest.approx(expected, abs=1e-6), good
