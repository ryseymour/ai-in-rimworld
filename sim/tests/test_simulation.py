"""The multi-day run: what the design says has to hold over time."""
from __future__ import annotations

import pytest

from colonysim.goods import GOOD_NAMES
from colonysim.simulation import build_simulation
from colonysim.trade import HOME

SEEDS = [1, 7, 23, 99]
DAYS = 150


def run(seed: int, days: int = DAYS, trade: bool = True, wildlife: bool = True):
    sim = build_simulation(seed=seed, wildlife=wildlife)
    sim.trade_enabled = trade
    start = sim.goods_in_world()
    coin = sim.coin_in_world()
    sim.run(days)
    return sim, start, coin


@pytest.mark.parametrize("seed", SEEDS)
def test_trade_never_creates_or_destroys_goods(seed):
    """The one defect most likely to hide in an exchange: a rounding slip that
    mints or eats goods. Everything on every shelf plus everything on the road
    must equal what was there, plus what was made, minus what was eaten -- by
    people or by animals. Nothing else may touch the total."""
    sim, start, _ = run(seed)
    end = sim.goods_in_world()

    for good in GOOD_NAMES:
        expected = (
            start[good]
            + sim.produced.get(good, 0.0)
            - sim.consumed.get(good, 0.0)
            - sim.lost.get(good, 0.0)
        )
        assert end[good] == pytest.approx(expected, abs=1e-6), good


@pytest.mark.parametrize("seed", SEEDS)
def test_a_world_without_animals_loses_nothing_at_all(seed):
    """Take the wolves off the map and the old invariant must come back
    exactly: with nothing on the roads to eat the cargo, trade alone can
    neither make nor destroy a single unit."""
    sim, start, coin = run(seed, wildlife=False)
    end = sim.goods_in_world()

    assert sim.lost == {}
    assert sim.escort_wages == 0.0
    assert sim.coin_in_world() == pytest.approx(coin, abs=1e-6)
    for good in GOOD_NAMES:
        expected = start[good] + sim.produced.get(good, 0.0) - sim.consumed.get(good, 0.0)
        assert end[good] == pytest.approx(expected, abs=1e-6), good


@pytest.mark.parametrize("seed", SEEDS)
def test_currency_is_conserved(seed):
    """Nothing in the world mints coin. The only coin that leaves the trading
    economy is what guards are paid, and that is counted."""
    sim, _, coin = run(seed)
    assert sim.coin_in_world() + sim.escort_wages == pytest.approx(coin, abs=1e-6)


@pytest.mark.parametrize("seed", SEEDS)
def test_trade_spreads_goods_more_evenly_than_no_trade(seed):
    """Everyone starts on their reserve, so the price gap between colonies
    opens up either way. The claim is that traders keep it narrower."""
    traded, _, _ = run(seed, trade=True)
    alone, _, _ = run(seed, trade=False)

    with_trade = sum(traded.price_spread(g) for g in GOOD_NAMES)
    without = sum(alone.price_spread(g) for g in GOOD_NAMES)
    assert with_trade < without


@pytest.mark.parametrize("seed", SEEDS)
def test_trade_keeps_colonies_fed(seed):
    """The point of the feature: a colony that cannot feed itself is supplied
    by one that can."""
    traded, _, _ = run(seed, trade=True)
    alone, _, _ = run(seed, trade=False)

    assert traded.hungry_colonies() == []
    assert alone.hungry_colonies(), "this world should starve without traders"


@pytest.mark.parametrize("seed", SEEDS)
def test_caravans_actually_travel(seed):
    sim, _, _ = run(seed)
    assert sim.journeys > 0


@pytest.mark.parametrize("seed", SEEDS)
def test_no_caravan_is_left_stranded(seed):
    """Every caravan either got home or is still on a journey that has not
    outlasted any plausible route."""
    sim, _, _ = run(seed)

    for caravan in sim.caravans:
        assert caravan.state != HOME
        age = sim.day - caravan.dispatched_day
        assert age < 60, f"caravan {caravan.id} has been out {age} days"


def test_the_whole_simulation_is_deterministic():
    """Encounters are the only dice in the sim, and they are seeded from the
    world, so two runs of a seed must agree down to the last coin."""
    a, _, _ = run(23, days=90)
    b, _, _ = run(23, days=90)

    assert a.journeys == b.journeys
    assert a.meetings == b.meetings
    assert a.lost == b.lost
    assert [c.storage.stock for c in a.colonies] == [c.storage.stock for c in b.colonies]
    assert [c.purse.amount for c in a.colonies] == [c.purse.amount for c in b.colonies]


def test_busy_routes_wear_into_better_roads():
    sim, _, _ = run(23)
    tiers = {tile.tier for tile in sim.network.tiles.values()}
    assert max(tiers) > 1, "no road was ever promoted by traffic"


def test_trade_moves_coin_between_colonies():
    """If every purse ends where it started, no one actually bought anything."""
    sim, _, _ = run(23)
    amounts = [c.purse.amount for c in sim.colonies]
    assert len(set(round(a, 3) for a in amounts)) > 1


def test_a_world_with_one_colony_still_runs():
    sim = build_simulation(seed=5, settlements=1)
    sim.run(30)
    assert sim.journeys == 0
