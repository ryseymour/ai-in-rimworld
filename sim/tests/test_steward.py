"""Stewards: what they can see of the network, and what they may change.

Two halves. First the mechanism -- a price, a reserve and a shift of labour are
each one number, and the rest of the sim has to honour all three. Then the
behaviour: what the scripted merchant does with them, and whether an economy
with someone running each colony ends up better stocked than one without.
"""
from __future__ import annotations

import pytest

from colonysim.goods import GOOD_NAMES, GOODS, RAW_GOOD_NAMES
from colonysim.money import SILVER, Purse
from colonysim.simulation import build_simulation
from colonysim.steward import (
    IMPORT_MARGIN,
    SLOW_INTERVAL,
    Link,
    NetworkView,
    Steward,
)
from colonysim.storage import (
    MAX_FOCUS,
    MAX_MARKUP,
    MIN_MARKUP,
    Colony,
    MarketView,
)
from colonysim.trade import CAPACITY, Caravan, do_business, plan_cargo
from colonysim.world import Settlement

SEEDS = [1, 7, 23, 99]


def colony(name="A", cid=0, coin=800.0, **stock) -> Colony:
    c = Colony(
        settlement=Settlement(cid, name, 5, 5),
        population=20,
        production={g: 0.0 for g in GOOD_NAMES},
        consumption={"food": 10.0, "wood": 4.0, "stone": 2.0, "cloth": 1.0, "tools": 0.5},
        purse=Purse(SILVER, coin),
    )
    for good, qty in stock.items():
        c.storage.add(good, qty)
    return c


def link(cid, name, prices=None, surplus=None, shortfall=None, day=0, **kwargs) -> Link:
    """One neighbour as a steward remembers it."""
    view = MarketView(
        prices={g: GOODS[g].base_price for g in GOOD_NAMES} | (prices or {}),
        surplus={g: 0.0 for g in GOOD_NAMES} | (surplus or {}),
        shortfall={g: 0.0 for g in GOOD_NAMES} | (shortfall or {}),
        day=day,
    )
    return Link(
        colony=cid,
        name=name,
        days=kwargs.get("days", 3.0),
        hazard=kwargs.get("hazard", 0.0),
        tier=kwargs.get("tier", 1.0),
        legs=(),
        market=view,
    )


def view(*links, day=10, home=0) -> NetworkView:
    return NetworkView(day=day, home=home, links={l.colony: l for l in links})


# -------------------------------------------------------------- the policy

def test_a_colony_with_no_steward_prices_exactly_as_before():
    """The whole of the control case: an untouched policy must be invisible."""
    c = colony(food=200.0)
    assert c.policy.is_default()
    for good in GOOD_NAMES:
        assert c.price(good) == c.scarcity_price(good)
        assert c.reserve_days(good) == GOODS[good].buffer_days
        assert c.output(good) == c.production[good]


def test_a_markup_moves_the_price_and_nothing_else():
    c = colony(food=200.0)
    plain = c.price("food")
    stock = c.storage.get("food")

    c.policy.set_markup("food", 1.5)
    assert c.price("food") == pytest.approx(plain * 1.5)
    assert c.storage.get("food") == stock
    assert c.price("wood") == c.scarcity_price("wood")


def test_a_steward_cannot_price_its_colony_out_of_the_world():
    """An agent driving this can ask for anything; the sim takes what it can
    live with and carries on."""
    c = colony(food=200.0)
    assert c.policy.set_markup("food", 40.0) == MAX_MARKUP
    assert c.policy.set_markup("food", 0.0) == MIN_MARKUP
    assert c.policy.set_markup("food", -3.0) == MIN_MARKUP


def test_the_price_ceiling_moves_with_the_stance():
    """Otherwise a colony that has bid its prices up to pull in supply is
    capped below what it just offered, and the bid does nothing."""
    c = colony(food=1.0)
    c.policy.set_markup("food", 1.6)
    assert c.price("food") <= c.price_ceiling("food") + 1e-9
    assert c.price_ceiling("food") > GOODS["food"].base_price * 3.0


def test_a_caravan_is_actually_paid_the_price_a_steward_set():
    """The mechanism the whole feature rests on: a stance on the shelf has to
    reach the moment money changes hands."""
    host = colony("host", 1, food=20.0)
    home = colony("home", 0)
    plain = Caravan(id=0, home=0, destination=1, legs=(), cargo={"food": 30.0})
    dear = Caravan(id=1, home=0, destination=1, legs=(), cargo={"food": 30.0})

    do_business(plain, host, home)
    paid_plain = host.purse.amount

    host = colony("host", 1, food=20.0)
    host.policy.set_markup("food", 1.5)
    before = host.purse.amount
    do_business(dear, host, home)
    paid_dear = before - host.purse.amount

    assert paid_dear > (before - paid_plain) * 1.3


def test_raising_a_price_fetches_a_caravan_that_would_not_have_bothered():
    """How a steward reaches a trader it has never met: the price it quotes is
    what somebody else does their sums on.

    Both colonies sit close to their reserve, so the gap between them is real
    but too thin to be worth a journey. The buyer bidding up is what turns it
    into one."""
    seller = colony("seller", 0, food=205.0)
    buyer = colony("buyer", 1, food=195.0)

    assert "food" not in plan_cargo(seller, buyer.market_view(0), CAPACITY)

    buyer.policy.set_markup("food", 1.3)
    assert plan_cargo(seller, buyer.market_view(0), CAPACITY)["food"] > 0


def test_a_deeper_reserve_turns_surplus_into_something_it_wants_to_buy():
    c = colony(food=250.0)
    assert c.surplus("food") > 0
    assert c.shortfall("food") == 0

    c.policy.set_reserve("food", 1.5)
    assert c.reserve_days("food") == pytest.approx(GOODS["food"].buffer_days * 1.5)
    assert c.surplus("food") == 0
    assert c.shortfall("food") > 0


def test_where_the_people_work_changes_what_the_colony_makes():
    c = colony()
    c.production = {g: 10.0 for g in GOOD_NAMES}
    c.policy.set_focus("food", 1.4)
    made, _ = c.live_day()
    assert made["food"] == pytest.approx(14.0)
    assert made["wood"] == pytest.approx(10.0)


def test_moving_people_between_jobs_never_conjures_any():
    """Focus is a reallocation, not a bonus. Whatever the colony's baseline
    output is worth at ordinary prices, it is still worth that afterwards."""
    c = colony()
    c.production = {"food": 20.0, "wood": 12.0, "stone": 5.0, "cloth": 3.0, "tools": 1.0}
    shares = c.labour_shares()
    before = sum(shares.values())

    c.policy.set_focus("tools", MAX_FOCUS)
    c.policy.set_focus("food", 1.3)
    c.policy.rebalance_focus(shares)

    after = sum(c.output(g) * GOODS[g].base_price for g in GOOD_NAMES)
    assert after == pytest.approx(before, rel=1e-6)
    assert c.output("tools") > c.production["tools"]


def test_a_policy_reports_only_what_it_actually_changed():
    c = colony()
    assert c.policy.is_default()
    c.policy.set_markup("food", 1.3)
    stance = c.policy.adjustments()
    assert stance["markup"] == {"food": 1.3}
    assert stance["reserve"] == {} and stance["focus"] == {}
    assert not c.policy.is_default()


# --------------------------------------------------------------- the view

def test_a_steward_sees_every_colony_it_can_reach_and_not_itself():
    sim = build_simulation(seed=23, settlements=3)
    seen = sim.network_view(0)

    assert 0 not in seen.links
    assert set(seen.links) == {1, 2}
    for reach in seen.links.values():
        assert reach.days >= 1
        assert 0.0 <= reach.hazard <= 1.0
        assert reach.legs, "a link with no road is not a link"


def test_what_a_steward_knows_of_a_market_is_what_a_caravan_brought_home():
    """Roads are live; markets are memory. A steward planning on a market it
    has not visited is planning on the optimistic default, and that is the
    source of every mistake it makes."""
    sim = build_simulation(seed=23, settlements=3)
    fresh = sim.network_view(0)
    assert all(not reach.visited for reach in fresh.links.values())

    while not any(c.known for c in sim.colonies):
        sim.step_day()

    home = next(c for c in sim.colonies if c.known)
    seen = sim.network_view(home.id)
    for other, remembered in home.known.items():
        assert seen.links[other].market is remembered
        assert seen.links[other].age(sim.day) >= 0


def test_a_steward_sees_its_own_caravans_and_no_one_elses():
    sim = build_simulation(seed=23, settlements=3)
    while len({c.home for c in sim.caravans}) < 2:
        sim.step_day()

    for colony_id in range(len(sim.colonies)):
        mine = sim.network_view(colony_id).caravans
        assert all(c.home == colony_id for c in mine)
        assert len(mine) == sum(1 for c in sim.caravans if c.home == colony_id)


def test_the_view_sorts_who_sells_who_buys_and_who_competes():
    cheap = link(1, "Cheap", prices={"wood": 1.0}, surplus={"wood": 50.0})
    dear = link(2, "Dear", prices={"wood": 2.0}, surplus={"wood": 40.0})
    wanting = link(3, "Wanting", prices={"wood": 3.0}, shortfall={"wood": 80.0})
    seen = view(cheap, dear, wanting)

    assert [l.colony for l in seen.sellers("wood")] == [1, 2]
    assert [l.colony for l in seen.buyers("wood")] == [3]
    assert [l.colony for l in seen.rivals("wood", buyer=3)] == [1, 2]
    assert seen.cheapest("wood").colony == 1
    assert seen.dearest("wood").colony == 3


def test_a_brief_says_what_the_steward_is_looking_at():
    """The text an agent would be handed. If it does not name the colony, what
    it holds and who it can reach, there is nothing to decide on."""
    sim = build_simulation(seed=23, settlements=3)
    sim.run(30)
    brief = sim.stewards[0].brief()

    assert sim.colonies[0].name in brief
    for good in GOOD_NAMES:
        assert good in brief
    for other in sim.colonies[1:]:
        assert other.name in brief


# ----------------------------------------------------------- the merchant

def steady(steward: Steward, seen: NetworkView, rounds: int = 25) -> None:
    """Show a steward the same news every day for a while.

    Stances move a third of the way to where the steward wants them, so nothing
    it decides is visible in one day. That is deliberate -- a price that jumps
    on one day's stock has traders chasing noise -- and it means testing what
    it decides means letting it settle.
    """
    for _ in range(rounds):
        steward.review(seen)


def test_a_colony_short_of_a_good_bids_high_enough_to_be_worth_the_trip():
    """The steward works backwards from the trader's own sum: the price here
    has to beat the price there by enough to be worth the road.

    Being short already lifts the price on its own. The bid is what happens
    when that is still not enough -- here the only colony with food to spare
    is dear, so scarcity alone would never fetch a caravan."""
    short = colony(food=100.0)
    supplier = link(1, "Supplier", prices={"food": 4.0}, surplus={"food": 300.0})
    steward = Steward(short)
    assert short.price("food") < 4.0

    steady(steward, view(supplier))

    assert short.policy.markup_for("food") > 1.05
    assert short.price("food") >= 4.0 * (1.0 + IMPORT_MARGIN) - 0.01


def test_a_colony_bids_less_hard_when_nobody_it_knows_has_any():
    """There is no point paying a premium into an empty region."""
    known = colony("known", food=100.0)
    blind = colony("blind", food=100.0)
    supplier = link(1, "Supplier", prices={"food": 4.0}, surplus={"food": 300.0})
    empty = link(1, "Empty", prices={"food": 4.0})

    steady(Steward(known), view(supplier))
    steady(Steward(blind), view(empty))

    assert blind.policy.markup_for("food") < known.policy.markup_for("food")


def test_a_colony_with_no_coin_does_not_pretend_it_can_outbid_anyone():
    """It would be paying in barter off the same shelves it is trying to
    fill, so the bid is a way of giving goods away."""
    broke = colony(coin=5.0, food=100.0)
    flush = colony(coin=800.0, food=100.0)
    supplier = link(1, "Supplier", prices={"food": 4.0}, surplus={"food": 300.0})

    steady(Steward(broke), view(supplier))
    steady(Steward(flush), view(supplier))

    assert broke.policy.markup_for("food") <= 1.15
    assert flush.policy.markup_for("food") > broke.policy.markup_for("food")


def test_a_colony_sitting_on_a_pile_undercuts_whoever_else_could_supply_it():
    """Two colonies with wood and one buyer for it is a competition, and the
    steward's answer to a competition is to be the cheaper one."""
    glutted = colony(wood=900.0)
    rival = link(1, "Rival", prices={"wood": 1.0}, surplus={"wood": 200.0})
    buyer = link(2, "Buyer", prices={"wood": 2.4}, shortfall={"wood": 150.0})
    steward = Steward(glutted)

    steady(steward, view(rival, buyer))

    assert glutted.policy.markup_for("wood") < 1.0
    assert glutted.price("wood") < rival.price("wood")


def test_a_stance_relaxes_once_the_reason_for_it_has_gone():
    """A markup that outlives its shortage is just a colony overcharging
    itself for its own imports."""
    c = colony(food=100.0)
    supplier = link(1, "Supplier", prices={"food": 4.0}, surplus={"food": 300.0})
    steward = Steward(c)
    steady(steward, view(supplier))
    bid = c.policy.markup_for("food")
    assert bid > 1.05

    c.storage.add("food", 400.0)  # a caravan arrives
    steady(steward, view(supplier))
    assert c.policy.markup_for("food") < bid


def test_a_colony_that_keeps_running_a_good_down_holds_more_of_it_back():
    lean = colony(food=30.0)
    steward = Steward(lean)
    steady(steward, view(link(1, "Elsewhere")), rounds=SLOW_INTERVAL * 6)

    assert lean.reserve_days("food") > GOODS["food"].buffer_days


def test_a_steward_puts_people_on_what_the_colony_keeps_running_out_of():
    """The loop that makes this an economy rather than a delivery service: a
    price that stays high stops being a reason to buy and becomes a reason to
    make. Terrain still decides how much good it does.

    Raw goods only, because this dial moves people between the fields, the
    forest and the quarry. A colony short of arrows answers that at the bench
    instead -- see `test_crafting.py`."""
    for seed in SEEDS:
        sim = build_simulation(seed=seed, settlements=3)
        sim.run(150)
        for colony_, steward in zip(sim.colonies, sim.stewards):
            leanest = min(RAW_GOOD_NAMES, key=steward.remembered)
            assert colony_.policy.focus_for(leanest) > 1.0, (
                f"{colony_.name} never put anyone on {leanest}"
            )


def test_a_steward_can_be_driven_by_something_that_is_not_this_code():
    """The seam milestone 4 plugs into. Whatever decides -- a player, a model,
    a rule nobody has written yet -- sees the same view and writes through the
    same clamped setters."""
    shown = []

    def agent(steward: Steward, seen: NetworkView) -> None:
        shown.append((steward.name, seen.day, len(seen.links)))  # name, day, reach
        steward.set_markup("cloth", 1.75, "the agent says so")

    sim = build_simulation(seed=5, settlements=3)
    sim.stewards = [Steward(c, decide=agent) for c in sim.colonies]
    sim.run(4)

    assert len(shown) == 4 * len(sim.colonies)
    assert all(reach == 2 for _, _, reach in shown)
    for colony_ in sim.colonies:
        assert colony_.policy.markup_for("cloth") == pytest.approx(1.75)


def test_clearing_a_stance_puts_the_colony_back_on_plain_scarcity():
    sim = build_simulation(seed=23, settlements=3)
    sim.run(60)
    steward = sim.stewards[0]
    assert not steward.colony.policy.is_default()

    steward.clear()
    assert steward.colony.policy.is_default()
    for good in GOOD_NAMES:
        assert steward.colony.price(good) == steward.colony.scarcity_price(good)


def test_a_steward_writes_down_why_it_did_what_it_did():
    sim = build_simulation(seed=23, settlements=3)
    sim.run(120)
    assert any(steward.log for steward in sim.stewards)
    for steward in sim.stewards:
        for line in steward.log:
            assert line.startswith("day ")


# -------------------------------------------------------------- the economy

def test_stewards_leave_fewer_colonies_with_nothing_on_the_shelf():
    """The claim worth making for the whole feature. Not that prices converge
    -- a steward bidding for supply pushes them apart on purpose -- but that
    fewer colonies run a good down to nothing when someone is watching.

    Counted every day rather than on the last one. A snapshot at day 150 across
    four seeds is a handful of events either way, and anything that lifts the
    stewardless world -- haggling did, since a negotiated price is below the
    posted one and a buyer's coin goes further, and so did colonies favouring
    the neighbours they trust -- can tie it without the claim being any less
    true. The same worlds, counted day by day, are not close.
    """
    led = bare = 0
    for seed in SEEDS:
        for stewards in (True, False):
            sim = build_simulation(seed=seed, stewards=stewards)
            empty = 0
            for _ in range(150):
                sim.step_day()
                empty += sum(
                    1
                    for good in GOOD_NAMES
                    for days in sim.days_of_stock(good)
                    if days < 1.0
                )
            if stewards:
                led += empty
            else:
                bare += empty
    assert led < bare


@pytest.mark.parametrize("seed", SEEDS)
def test_a_steward_can_feed_a_colony_trade_cannot_reach(seed):
    """Cut the roads and a colony with no steward starves on what its land
    happens to make. One with a steward moves people into the fields."""
    led = build_simulation(seed=seed)
    led.trade_enabled = False
    led.run(150)

    bare = build_simulation(seed=seed, stewards=False)
    bare.trade_enabled = False
    bare.run(150)

    assert len(led.hungry_colonies()) < len(bare.hungry_colonies())


@pytest.mark.parametrize("seed", SEEDS)
def test_stewards_do_not_create_or_destroy_anything(seed):
    """Conservation again, because stewards move production and prices, and a
    slip in either is exactly how a world starts minting food."""
    sim = build_simulation(seed=seed)
    start = sim.goods_in_world()
    coin = sim.coin_in_world()
    sim.run(120)
    end = sim.goods_in_world()

    for good in GOOD_NAMES:
        expected = (
            start[good]
            + sim.produced.get(good, 0.0)
            - sim.consumed.get(good, 0.0)
            - sim.lost.get(good, 0.0)
        )
        assert end[good] == pytest.approx(expected, abs=1e-6), good
    assert sim.coin_in_world() + sim.escort_wages == pytest.approx(coin, abs=1e-6)


def test_a_steward_run_world_still_replays_exactly():
    a = build_simulation(seed=23, settlements=3)
    b = build_simulation(seed=23, settlements=3)
    a.run(90)
    b.run(90)

    assert [c.storage.stock for c in a.colonies] == [c.storage.stock for c in b.colonies]
    assert [c.policy.markup for c in a.colonies] == [c.policy.markup for c in b.colonies]
    assert [c.policy.focus for c in a.colonies] == [c.policy.focus for c in b.colonies]
    assert [s.log for s in a.stewards] == [s.log for s in b.stewards]


def test_three_colonies_end_up_doing_different_things():
    """Ryan's world: three villages, one economy. Each one should end the run
    with its own prices and its own stance, not three copies of the average."""
    sim = build_simulation(seed=23, settlements=3)
    sim.run(150)

    assert len(sim.colonies) == 3
    assert all(not c.policy.is_default() for c in sim.colonies)
    for good in ("food", "wood"):
        quoted = {round(c.price(good), 3) for c in sim.colonies}
        assert len(quoted) == 3, f"every colony quotes the same for {good}"
    assert sim.journeys > 0


def test_the_viewer_shows_what_each_steward_has_done():
    from colonysim.server import state_payload

    sim = build_simulation(seed=23, settlements=3)
    sim.run(120)
    panel = state_payload(sim)["stewards"]

    assert [row["name"] for row in panel] == [c.name for c in sim.colonies]
    assert any(row["prices"] or row["working"] or row["holding"] for row in panel)
    for row in panel:
        for quote in row["prices"]:
            assert MIN_MARKUP <= quote["at"] <= MAX_MARKUP


def test_a_world_with_nobody_in_charge_still_runs():
    sim = build_simulation(seed=23, settlements=3, stewards=False)
    sim.run(60)
    assert sim.stewards == []
    assert all(c.policy.is_default() for c in sim.colonies)
