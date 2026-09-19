"""Reputation: what colonies make of each other, and what it costs them.

Three halves, in the order the feature was built. The ledger itself -- one
number per pair, moved only by conduct and faded only by time. Then what the
trade code does with it: the price at the counter, the caravan that is turned
away at the gate, the guards two colonies share. Then the claim that matters:
misconduct is a lasting cost and not a bad afternoon.
"""
from __future__ import annotations

import pytest

from colonysim.goods import GOOD_NAMES, GOODS
from colonysim.money import SILVER, Purse
from colonysim.reputation import (
    DEAL_SIZE,
    EMBARGO,
    SHORT_LOSS,
    FRIENDLY,
    Reputation,
    describe,
    favour,
    guard_discount,
    trade_bias,
    trades_with,
)
from colonysim.server import STANDING_ROWS, standing_payload, state_payload
from colonysim.simulation import build_simulation
from colonysim.steward import Link, NetworkView, Steward
from colonysim.storage import Colony, MarketView
from colonysim.trade import Caravan, do_business
from colonysim.wildlife import escort_cost
from colonysim.world import Settlement

SEEDS = [1, 7, 23, 99]


def colony(name="A", cid=0, coin=4000.0, **stock) -> Colony:
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


def link(cid, name, standing=0.0, surplus=None, shortfall=None) -> Link:
    view = MarketView(
        prices={g: GOODS[g].base_price for g in GOOD_NAMES},
        surplus={g: 0.0 for g in GOOD_NAMES} | (surplus or {}),
        shortfall={g: 0.0 for g in GOOD_NAMES} | (shortfall or {}),
        day=1,
    )
    return Link(
        colony=cid,
        name=name,
        days=3.0,
        hazard=0.0,
        tier=1.0,
        legs=(),
        market=view,
        standing=standing,
    )


def visit(seller: Colony, buyer: Colony, qty=50.0, hazard=0.0, day=1) -> Caravan:
    """One caravan from `seller` to `buyer`, there and dealt with."""
    caravan = Caravan(
        id=0, home=seller.id, destination=buyer.id, legs=(), hazard=hazard
    )
    caravan.cargo["food"] = seller.storage.remove("food", qty)
    do_business(caravan, buyer, seller, day=day)
    return caravan


# ------------------------------------------------------------------ the scale

def test_the_scale_reads_as_words():
    assert describe(0.0) == "neutral"
    assert describe(0.9) == "trusted"
    assert describe(-0.3) == "wary"
    assert describe(-0.9) == "shunned"


def test_everyone_starts_a_stranger():
    ledger = Reputation()
    assert ledger.of(3) == 0.0
    assert ledger.trades_with(3)
    assert ledger.favour(3) == 1.0
    assert ledger.known() == {}


def test_an_opinion_is_clamped_and_written_down():
    ledger = Reputation()
    ledger.record(4, 1, "Ashford", "fair", 0.4, "dealt well")
    assert ledger.of(1) == pytest.approx(0.4)

    ledger.record(5, 1, "Ashford", "fair", 5.0, "dealt well again")
    assert ledger.of(1) == 1.0  # nobody is better than trusted
    assert [r.kind for r in ledger.about(1)] == ["fair", "fair"]
    assert "Ashford" in ledger.remarks[-1].describe()


def test_a_ledger_that_is_off_never_forms_an_opinion():
    """The control case: with nobody keeping score every read is neutral, so
    every piece of trade code behaves as it did before this existed."""
    ledger = Reputation(enabled=False)
    ledger.judge_deal(1, 2, "Fenwick", paid=500.0, honest=100.0)
    ledger.refused(2, 2, "Fenwick")
    assert ledger.of(2) == 0.0
    assert ledger.remarks == []


def test_opinions_fade_toward_neutral_and_are_forgotten():
    ledger = Reputation()
    ledger.record(1, 1, "Ashford", "fair", 0.5, "dealt well")
    ledger.record(1, 2, "Brackwater", "gouged", -0.004, "charged a shade over")

    ledger.decay()
    assert 0.49 < ledger.of(1) < 0.5
    # An opinion that has essentially arrived back at neutral stops being one.
    assert 2 not in ledger.scores

    for _ in range(400):
        ledger.decay()
    assert ledger.of(1) < 0.2


# ------------------------------------------------------------------- judging

def test_dealing_at_the_hosts_own_price_earns_goodwill():
    ledger = Reputation()
    ledger.judge_deal(3, 1, "Ashford", paid=DEAL_SIZE, honest=DEAL_SIZE)
    assert ledger.of(1) > 0
    assert ledger.remarks[-1].kind == "fair"


def test_charging_well_over_the_hosts_own_price_is_remembered_as_gouging():
    ledger = Reputation()
    ledger.judge_deal(3, 1, "Ashford", paid=DEAL_SIZE * 1.4, honest=DEAL_SIZE)
    assert ledger.of(1) < 0
    assert ledger.remarks[-1].kind == "gouged"


def test_a_small_premium_for_a_hard_road_is_not_gouging():
    """Traders charge for danger -- `trade.MAX_RISK_PREMIUM` is the whole
    reason a caravan will walk a wolf road at all. A modest premium has to
    stay inside what a host will wear, or the wildlife would embargo the
    world by itself."""
    ledger = Reputation()
    ledger.judge_deal(3, 1, "Ashford", paid=DEAL_SIZE * 1.05, honest=DEAL_SIZE)
    assert ledger.of(1) > 0


def test_a_bigger_deal_moves_an_opinion_further():
    small, large = Reputation(), Reputation()
    small.judge_deal(1, 1, "Ashford", paid=DEAL_SIZE * 0.2, honest=DEAL_SIZE * 0.2)
    large.judge_deal(1, 1, "Ashford", paid=DEAL_SIZE * 4, honest=DEAL_SIZE * 4)
    assert large.of(1) > small.of(1) * 2


def test_an_unpaid_bill_is_a_credit_mark_and_gouging_is_the_real_offence():
    """A colony only fails to cover a bill when it has neither coin nor
    anything above its reserve to hand over, which makes it broke rather than
    dishonest -- and this sim cannot tell those apart. So an unpaid bill is
    worth less against a colony than deliberately overcharging one, and on its
    own it must not be enough to close a gate."""
    owing = Reputation()
    for day in range(1, 6):
        owing.judge_payment(day, 1, "Ashford", bill=DEAL_SIZE * 4, shortfall=DEAL_SIZE * 4)
    gouging = Reputation()
    gouging.judge_deal(2, 1, "Ashford", paid=DEAL_SIZE * 2.8, honest=DEAL_SIZE * 2)

    assert owing.of(1) < 0
    assert gouging.of(1) < -SHORT_LOSS
    assert owing.remarks[0].change > -SHORT_LOSS - 0.001


def test_a_bill_covered_in_full_is_worth_a_little_goodwill():
    """Most of the goodwill in this world is made of ordinary bills paid on
    the day -- and a slip is still worth several of them."""
    paid_up = Reputation()
    paid_up.judge_payment(2, 1, "Ashford", bill=200.0, shortfall=0.0)
    assert paid_up.of(1) > 0

    owing = Reputation()
    owing.judge_payment(2, 1, "Ashford", bill=200.0, shortfall=200.0)
    assert abs(owing.of(1)) > paid_up.of(1)


def test_buying_at_the_asking_price_is_good_custom_on_both_sides():
    """A caravan that turns up with coin and pays what is asked is somebody
    both colonies want back."""
    home = colony("Home", 0, food=10)
    host = colony("Host", 1, food=900)
    caravan = Caravan(id=0, home=0, destination=1, legs=())
    home.purse.transfer_to(caravan.purse, 300.0)

    do_business(caravan, host, home, day=4)

    assert host.reputation.of(0) > 0
    assert home.reputation.of(1) > 0
    assert host.reputation.remarks[-1].kind == "custom"


# ------------------------------------------------------- what standing buys

def test_the_price_at_the_counter_follows_standing():
    assert favour(1.0) > 1.0 > favour(-1.0)
    assert favour(0.0) == 1.0


def test_only_real_goodwill_shares_guards():
    assert guard_discount(0.0) == 0.0
    assert guard_discount(FRIENDLY) == 0.0
    assert 0.0 < guard_discount(0.6) < guard_discount(1.0) < 1.0


def test_a_colony_below_the_embargo_line_is_not_dealt_with():
    assert trades_with(EMBARGO + 0.01)
    assert not trades_with(EMBARGO - 0.01)
    assert trade_bias(0.8) > trade_bias(0.0) > trade_bias(-0.5) > 0


def test_a_trusted_caravan_is_paid_better_than_a_distrusted_one():
    """The same goods, the same shelves, the same day. All that differs is
    what the host thinks of where the caravan came from."""
    earnings = {}
    for standing in (0.9, -0.4):
        seller = colony("Seller", 0, food=600)
        buyer = colony("Buyer", 1, food=40)
        buyer.reputation.scores[0] = standing
        earnings[standing] = visit(seller, buyer).purse.amount

    assert earnings[0.9] > earnings[-0.4] > 0


def test_a_trusted_caravan_buys_here_for_less():
    """The other side of the same counter: goodwill is a discount when the
    caravan is the one handing over coin."""
    spend = {}
    for standing in (0.9, -0.4):
        home = colony("Home", 0, food=10)
        host = colony("Host", 1, food=900)
        host.reputation.scores[0] = standing
        caravan = Caravan(id=0, home=0, destination=1, legs=())
        home.purse.transfer_to(caravan.purse, 400.0)
        do_business(caravan, host, home, day=1)
        spend[standing] = 400.0 - caravan.purse.amount

    assert spend[0.9] < spend[-0.4]


def test_standing_does_not_move_goods_or_coin_that_are_not_there():
    """Whatever the price, a deal is still a swap: nothing is minted at either
    end of the scale."""
    for standing in (1.0, 0.0, -0.5):
        seller = colony("Seller", 0, food=600)
        buyer = colony("Buyer", 1, food=40)
        buyer.reputation.scores[0] = standing
        goods = seller.storage.get("food") + buyer.storage.get("food")
        coin = seller.purse.amount + buyer.purse.amount

        caravan = visit(seller, buyer)

        after_goods = (
            seller.storage.get("food")
            + buyer.storage.get("food")
            + caravan.cargo.get("food", 0.0)
        )
        after_coin = seller.purse.amount + buyer.purse.amount + caravan.purse.amount
        assert after_goods == pytest.approx(goods)
        assert after_coin == pytest.approx(coin)


# --------------------------------------------------------- the gate is shut

def test_a_shunned_caravan_is_turned_away_at_the_gate():
    seller = colony("Seller", 0, food=600)
    buyer = colony("Buyer", 1, food=40)
    buyer.reputation.scores[0] = EMBARGO - 0.2

    caravan = visit(seller, buyer)

    assert caravan.cargo["food"] == pytest.approx(50)  # nothing changed hands
    assert buyer.storage.get("food") == pytest.approx(40)
    assert "turned away" in caravan.ledger[0]


def test_being_turned_away_is_itself_remembered():
    seller = colony("Seller", 0, food=600)
    buyer = colony("Buyer", 1, food=40)
    buyer.reputation.scores[0] = EMBARGO - 0.2

    visit(seller, buyer, day=5)
    assert seller.reputation.of(1) < 0
    assert seller.reputation.remarks[-1].kind == "refused"
    # It still learns what the market looked like: it got as far as the gate.
    assert seller.known[1].day == 5


def test_gouging_a_colony_for_long_enough_closes_its_gate():
    """The whole arc in one test. A caravan on a road so dangerous it charges
    the full premium, visit after visit, until the host stops letting it in --
    and then, a year of quiet later, lets it in again."""
    seller = colony("Seller", 0, food=4000)
    buyer = colony("Buyer", 1, food=40)

    for day in range(1, 9):
        buyer.storage.stock["food"] = 40.0  # the buyer eats what it bought
        caravan = visit(seller, buyer, qty=80.0, hazard=1.0, day=day)
        if "turned away" in caravan.ledger[0]:
            break
    else:
        pytest.fail("a caravan charging the full premium was never turned away")

    assert buyer.reputation.of(0) <= EMBARGO
    assert buyer.reputation.word_for(0) == "shunned"

    for _ in range(365):
        buyer.reputation.decay()
    assert buyer.reputation.trades_with(0)  # a grudge, not a blood feud


def test_a_grudge_outlasts_a_season():
    """The point of the decay rate: a colony that cheated in the spring is
    still paying for it when the roads dry out again."""
    ledger = Reputation()
    ledger.record(1, 1, "Ashford", "gouged", -0.8, "charged over the odds")
    for _ in range(90):
        ledger.decay()
    assert ledger.of(1) < -0.5


# ------------------------------------------------------------ the steward

def test_a_steward_does_not_bid_for_a_caravan_it_would_turn_away():
    """`sellers` is what the merchant works its import price back from. A
    colony it has written off is not a supplier, whatever it has to spare."""
    view = NetworkView(
        day=10,
        home=0,
        links={
            1: link(1, "Shunned", standing=EMBARGO - 0.1, surplus={"food": 200.0}),
            2: link(2, "Welcome", standing=0.4, surplus={"food": 200.0}),
        },
    )
    assert [l.colony for l in view.sellers("food")] == [2]
    assert view.cheapest("food").colony == 2


def test_a_steward_does_not_undercut_for_a_buyer_it_would_turn_away():
    view = NetworkView(
        day=10,
        home=0,
        links={
            1: link(1, "Shunned", standing=EMBARGO - 0.1, shortfall={"wood": 90.0}),
            2: link(2, "Welcome", standing=0.1, shortfall={"wood": 40.0}),
        },
    )
    assert [l.colony for l in view.buyers("wood")] == [2]


def test_a_rival_is_a_rival_whatever_we_think_of_them():
    """Writing a colony off does not stop it supplying somebody else, so it
    still counts when the steward works out what it is bidding against."""
    view = NetworkView(
        day=10,
        home=0,
        links={
            1: link(1, "Shunned", standing=EMBARGO - 0.1, surplus={"food": 200.0}),
            2: link(2, "Buyer", standing=0.1, shortfall={"food": 60.0}),
        },
    )
    assert [l.colony for l in view.rivals("food", buyer=2)] == [1]


def test_the_brief_says_what_the_colony_makes_of_each_neighbour():
    """The brief is the prompt an agent-driven steward decides from, so
    standing has to be in it in words, not only in the numbers it moves."""
    home = colony("Home", 0, food=300)
    steward = Steward(home)
    steward.review(
        NetworkView(day=4, home=0, links={1: link(1, "Ashford", standing=0.8)})
    )
    assert "trusted" in steward.brief()
    assert steward.regard_for(1) == 0.0  # its own ledger, not the view's


# ------------------------------------------------------------- the world

def test_opinions_fade_every_day_the_world_runs():
    sim = build_simulation(seed=23, settlements=3)
    sim.colonies[0].reputation.scores[1] = 0.6
    sim.step_day()
    assert sim.colonies[0].reputation.of(1) < 0.6


def test_a_colony_sends_nobody_to_a_neighbour_it_has_written_off():
    sim = build_simulation(seed=23, settlements=3)
    sim.colonies[0].reputation.scores[1] = -0.95

    sent = set()
    for _ in range(120):
        sim.step_day()
        sent |= {(c.home, c.destination) for c in sim.caravans}

    assert (0, 1) not in sent
    assert sent, "the world stopped trading altogether"


def test_guards_come_cheaper_between_colonies_that_trust_each_other():
    sim = build_simulation(seed=23, settlements=3)
    plain = sim._escort_wage(sim.colonies[0], 1, days=6)
    assert plain == pytest.approx(escort_cost(6))

    sim.colonies[0].reputation.scores[1] = 0.9
    assert sim._escort_wage(sim.colonies[0], 1, days=6) == pytest.approx(plain)

    # It takes goodwill at both ends: guards are shared, not given.
    sim.colonies[1].reputation.scores[0] = 0.9
    assert sim._escort_wage(sim.colonies[0], 1, days=6) < plain


@pytest.mark.parametrize("seed", SEEDS)
def test_trading_fairly_is_what_earns_a_good_name(seed):
    """Left alone, colonies pay their bills and deal at each other's prices,
    and the pairs that deal most end up thinking best of each other.

    The claim is about the ordinary case: an honest world is not one where
    everyone ends up hated, and a caravan is not turned away for having done
    nothing wrong."""
    sim = build_simulation(seed=seed)
    sim.run(250)

    standings = sim.standings()
    assert standings, "nobody formed an opinion of anybody"
    assert max(standing for _, _, standing in standings) > 0.1
    assert sim.refusals == 0


def test_the_pair_that_trades_most_is_the_pair_that_trusts_most():
    """Standing is built out of dealings, so it has to follow them: the
    neighbours a colony actually trades with are the ones it thinks well of,
    and a colony it has never met is nobody to it."""
    sim = build_simulation(seed=23)
    sim.run(250)

    best = max(sim.standings(), key=lambda row: row[2])
    assert best[2] > 0.3
    assert sim.colonies[best[0]].reputation.about(best[1])


@pytest.mark.parametrize("seed", SEEDS)
def test_a_world_where_nobody_keeps_score_still_trades(seed):
    """The control case. Reputation off must leave a working economy, so any
    difference between the two worlds is reputation's doing and not a bug it
    is covering for."""
    sim = build_simulation(seed=seed, settlements=3, reputation=False)
    sim.run(150)

    assert sim.standings() == []
    assert sim.refusals == 0
    assert sim.journeys > 0


def test_the_viewer_shows_who_thinks_what_of_whom():
    """The panel beside the map is where a player reads this at all, so the
    payload has to carry the standing, the word for it, and the last thing
    that moved it."""
    sim = build_simulation(seed=23)
    sim.run(200)

    rows = standing_payload(sim)
    assert rows, "the panel would say everyone is still a stranger"
    assert len(rows) <= STANDING_ROWS
    assert rows == sorted(rows, key=lambda row: row["at"])  # worst first
    assert {"from", "to", "at", "word", "note"} == set(rows[0])
    assert rows[0]["word"] == describe(rows[0]["at"])
    assert any(row["note"] for row in rows)

    state = state_payload(sim)
    assert state["standing"] == rows
    assert state["refusals"] == sim.refusals


def test_a_world_where_nobody_keeps_score_shows_an_empty_panel():
    sim = build_simulation(seed=23, reputation=False)
    sim.run(60)
    assert standing_payload(sim) == []


@pytest.mark.parametrize("seed", SEEDS)
def test_keeping_score_starves_nobody_who_would_have_eaten_without_it(seed):
    """The check on the whole feedback loop. Standing shuts gates, and the
    colony most likely to have one shut on it is the poorest one -- which is
    also the one least able to survive it. Whatever reputation costs a badly
    behaved colony, it must not be the thing that empties a granary that the
    same world keeps full without it."""
    for settlements in (3, 6):
        scored = build_simulation(seed=seed, settlements=settlements)
        plain = build_simulation(seed=seed, settlements=settlements, reputation=False)
        scored.run(300)
        plain.run(300)
        assert set(scored.hungry_colonies()) <= set(plain.hungry_colonies())


@pytest.mark.parametrize("seed", SEEDS)
def test_keeping_score_does_not_create_or_destroy_goods(seed):
    """Conservation again, with the prices now moving on what colonies think
    of each other: a favour at the counter is a different price, never a
    different quantity."""
    sim = build_simulation(seed=seed, settlements=3)
    start = sim.goods_in_world()
    coin = sim.coin_in_world()
    sim.run(150)
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
