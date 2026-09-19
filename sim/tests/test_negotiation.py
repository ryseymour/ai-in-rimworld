"""Haggling: the dialogue, the deal that comes out of it, and the seam.

The claim this file exists to check is not that negotiation produces nicer
numbers. It is that a price is now the outcome of two positions and two
temperaments, that neither side can be talked past its own limit, and that
whatever is doing the talking -- the scripted negotiator, a test double, a
model -- the rest of the simulation cannot be damaged by it.
"""
from __future__ import annotations

import pytest

from colonysim.goods import GOODS
from colonysim.money import SILVER, Purse
from colonysim.negotiation import (
    ACCEPT,
    COUNTER,
    HOST,
    MAX_ROUNDS,
    OPEN,
    TRADER,
    WALK,
    Haggle,
    Move,
    Seat,
    Speakers,
    negotiate,
)
from colonysim.simulation import NEGOTIATIONS_KEPT, build_simulation
from colonysim.storage import MAX_MULT, Colony, Storage
from colonysim.steward import Steward
from colonysim.trade import Caravan, do_business
from colonysim.world import Settlement


def colony(name="A", cid=0, coin=500.0, **stock) -> Colony:
    c = Colony(
        settlement=Settlement(cid, name, 5, 5),
        population=20,
        production={g: 0.0 for g in GOODS},
        consumption={"food": 10.0, "wood": 4.0, "stone": 2.0, "cloth": 1.0, "tools": 0.5},
        storage=Storage(),
        purse=Purse(SILVER, coin),
    )
    for good, qty in stock.items():
        c.storage.add(good, qty)
    return c


def table(
    trader_limit=1.0,
    trader_open=4.0,
    host_open=1.5,
    host_limit=4.0,
    want=10.0,
    trader_eager=0.5,
    host_eager=0.5,
    good="food",
) -> Haggle:
    """A table with the numbers stated outright, rather than derived from a
    colony -- so a test about temperament is about temperament alone."""
    return Haggle(
        good=good,
        day=1,
        trader=Seat(TRADER, "Cart", limit=trader_limit, aspiration=trader_open,
                    want=want, quote=trader_limit, eagerness=trader_eager),
        host=Seat(HOST, "Village", limit=host_limit, aspiration=host_open,
                  want=want, quote=host_open, eagerness=host_eager),
    )


# ------------------------------------------------------------------- seats

def test_a_seat_walks_from_what_it_wants_to_what_it_will_bear():
    """The schedule the whole thing terminates on: by its last turn every
    negotiator is standing on its own limit, whatever its temperament."""
    seat = Seat(TRADER, "Cart", limit=2.0, aspiration=6.0, want=10.0)
    assert seat.position(0, MAX_ROUNDS) == pytest.approx(6.0)
    assert seat.position(MAX_ROUNDS, MAX_ROUNDS) == pytest.approx(2.0)
    assert seat.position(99, MAX_ROUNDS) == pytest.approx(2.0)

    walk = [seat.position(turn, MAX_ROUNDS) for turn in range(MAX_ROUNDS + 1)]
    assert walk == sorted(walk, reverse=True), "a seller's asks only come down"


def test_the_side_that_needs_the_deal_gives_ground_first():
    """Eagerness is the only thing that differs between two otherwise identical
    negotiators, and the only reason one of them does worse."""
    desperate = Seat(HOST, "V", limit=4.0, aspiration=2.0, want=1.0, eagerness=1.0)
    comfortable = Seat(HOST, "V", limit=4.0, aspiration=2.0, want=1.0, eagerness=0.0)

    assert desperate.patience < comfortable.patience
    for turn in (1, 2, 3):
        assert desperate.position(turn, MAX_ROUNDS) > comfortable.position(
            turn, MAX_ROUNDS
        ), "the desperate buyer is bidding higher by now"


def test_a_buyer_that_dislikes_the_price_buys_less_of_it():
    """A price a colony hates does not stop it buying; it makes it buy less --
    unless it is short enough that it has to take what it can get."""
    picky = Seat(HOST, "V", limit=4.0, aspiration=2.0, want=100.0, quote=2.0,
                 eagerness=0.0)
    assert picky.appetite(2.0) == pytest.approx(100.0)
    assert picky.appetite(4.0) < 60.0

    starving = Seat(HOST, "V", limit=4.0, aspiration=2.0, want=100.0, quote=2.0,
                    eagerness=1.0)
    assert starving.appetite(4.0) == pytest.approx(100.0)

    seller = Seat(TRADER, "Cart", limit=1.0, aspiration=4.0, want=100.0, quote=1.0)
    assert seller.appetite(1.0) == pytest.approx(100.0), "a seller wants to sell it all"


# ------------------------------------------------------------ what is allowed

def test_a_negotiator_cannot_say_anything_that_breaks_the_table():
    """The same principle as the clamped policy setters: whatever is doing the
    talking may be wrong, rude or absurd, and the worst it can do is make a bad
    deal."""
    haggle = table(want=10.0)
    played = haggle.play(Move(TRADER, "bellow", price=10_000.0, qty=999.0, line="x" * 500))

    assert played.act == COUNTER, "an act nobody has heard of is just an offer"
    assert played.price <= max(haggle.trader.aspiration, haggle.host.limit)
    assert played.qty <= 10.0
    assert len(played.line) <= 160


def test_accepting_means_the_terms_that_were_actually_offered():
    """Otherwise 'I accept, at my own price, for twice the cart' is a legal
    move, and every negotiator learns to say it."""
    haggle = table()
    haggle.play(Move(TRADER, OPEN, price=3.0, qty=8.0, line="three."))
    taken = haggle.play(Move(HOST, ACCEPT, price=0.01, qty=999.0, line="done."))

    assert (taken.price, taken.qty) == (3.0, 8.0)
    assert haggle.price == 3.0 and haggle.qty == 8.0


def test_accepting_before_anything_is_offered_is_just_an_opening():
    haggle = table()
    played = haggle.play(Move(HOST, ACCEPT, price=2.0, qty=4.0, line="fine."))

    assert played.act == OPEN
    assert not haggle.over


# ------------------------------------------------------------- the dialogue

def test_a_deal_is_struck_between_the_two_limits_and_never_outside_them():
    haggle = negotiate(table(trader_limit=1.0, host_limit=4.0))

    assert haggle.settled
    assert 1.0 <= haggle.price <= 4.0
    assert haggle.moves[-1].act == ACCEPT


@pytest.mark.parametrize("trader_limit", [0.5, 1.0, 2.0, 3.0])
@pytest.mark.parametrize("host_limit", [2.5, 4.0, 6.0])
@pytest.mark.parametrize("eager", [0.0, 0.5, 1.0])
def test_a_deal_happens_exactly_when_the_limits_overlap(trader_limit, host_limit, eager):
    """The property that keeps the economy running: if there is a price both
    sides could live with, the scripted negotiators find one -- temperament
    changes what the price is, never whether there is one. And if there is not,
    they find that out and stop, rather than one of them crossing its limit."""
    haggle = negotiate(
        table(
            trader_limit=trader_limit,
            trader_open=host_limit,
            host_open=trader_limit,
            host_limit=host_limit,
            trader_eager=eager,
            host_eager=1.0 - eager,
        )
    )
    if trader_limit > host_limit:
        assert not haggle.settled, haggle.transcript()
        return
    assert haggle.settled, haggle.transcript()
    assert trader_limit - 1e-9 <= haggle.price <= host_limit + 1e-9


def test_limits_that_do_not_overlap_end_in_no_deal():
    """A trip that did not pay. The sim had no way to express this before: the
    cargo simply goes home again."""
    haggle = negotiate(table(trader_limit=5.0, trader_open=5.0, host_limit=3.0))

    assert not haggle.settled
    assert haggle.closed == WALK
    assert haggle.moves[-1].act == WALK
    assert haggle.transcript(), "somebody has to say why they are leaving"


def test_the_exchange_is_short_and_alternates():
    haggle = negotiate(table())
    speakers = [move.speaker for move in haggle.moves]

    assert speakers[0] == TRADER, "the one who turned up speaks first"
    assert all(a != b for a, b in zip(speakers, speakers[1:])), "they take turns"
    assert len(haggle.moves) <= 2 * (MAX_ROUNDS + 1) + 2


def test_the_side_in_more_of_a_hurry_does_worse_out_of_it():
    """The reason the dialogue is worth simulating rather than splitting the
    difference: a colony four days from an empty granary pays for being four
    days from an empty granary."""
    calm = negotiate(table(host_eager=0.0, trader_eager=0.5))
    frantic = negotiate(table(host_eager=1.0, trader_eager=0.5))

    assert calm.settled and frantic.settled
    assert frantic.price > calm.price


def test_the_same_table_always_has_the_same_argument():
    """A seeded world has to replay word for word, so nothing at the counter
    may be random."""
    first = negotiate(table())
    again = negotiate(table())

    assert first.transcript() == again.transcript()
    assert first.price == again.price


def test_a_brief_gives_a_negotiator_what_it_needs_to_answer():
    """The text a model is handed. Without the good, the limit and what is on
    the table, there is nothing to decide."""
    haggle = table(good="cloth")
    haggle.play(Move(TRADER, OPEN, price=3.5, qty=6.0, line="three fifty."))
    brief = haggle.brief(HOST)

    assert "cloth" in brief
    assert "Village" in brief and "Cart" in brief
    assert "4.00" in brief, "its own limit"
    assert "3.50" in brief, "what it has been offered"
    assert "three fifty." in brief, "and what was said"


# ------------------------------------------------------ at an actual counter

def test_a_negotiated_sale_moves_goods_and_coin_without_creating_any():
    """Conservation again, because the price is now a decision and a slip in
    it is exactly how a world starts minting food."""
    home = colony("Home", 0, food=600)
    host = colony("Host", 1, food=40)
    caravan = Caravan(id=0, home=0, destination=1, legs=())
    caravan.cargo["food"] = home.storage.remove("food", 300)
    caravan.basis["food"] = 2.0
    home.purse.transfer_to(caravan.purse, 200.0)

    goods = lambda: (  # noqa: E731 - a one-line total, three times over
        home.storage.get("food") + host.storage.get("food") + caravan.cargo.get("food", 0)
    )
    coin = lambda: home.purse.amount + host.purse.amount + caravan.purse.amount  # noqa: E731
    before_goods, before_coin = goods(), coin()

    do_business(caravan, host, home, day=1)

    assert goods() == pytest.approx(before_goods)
    assert coin() == pytest.approx(before_coin)


def test_goods_nobody_would_pay_for_go_home_on_the_cart():
    """The trader holds out for what the cargo was worth at home. If the host
    cannot reach that, the trip did not pay and the cargo is still cargo."""
    home = colony("Home", 0)
    host = colony("Host", 1, food=190)  # barely short, so it quotes low
    caravan = Caravan(id=0, home=0, destination=1, legs=(), cargo={"food": 50.0})
    caravan.basis["food"] = GOODS["food"].base_price * MAX_MULT  # dear at home

    before = host.purse.amount
    do_business(caravan, host, home, day=1)

    assert caravan.cargo["food"] == pytest.approx(50.0)
    assert host.purse.amount == before
    assert any("no deal" in line for line in caravan.ledger)


def test_a_host_is_never_talked_above_what_the_good_can_fetch_there():
    """The ceiling is the host's last defence, and the negotiation sits inside
    it rather than around it."""
    host = colony("Host", 1)  # empty store, already quoting the ceiling
    caravan = Caravan(id=0, home=0, destination=1, legs=(), cargo={"food": 10.0})
    before = host.purse.amount

    do_business(caravan, host, colony("Home", 0), day=1)

    paid = before - host.purse.amount
    assert paid <= 10.0 * GOODS["food"].base_price * MAX_MULT + 1e-6


def test_what_the_cargo_cost_at_home_is_what_the_trader_holds_out_for():
    """Two identical carts at an identical counter. The one whose goods were
    nearly this dear at home has nothing to give, and gets more for them."""
    settled = []
    for basis in (0.5, 3.0):
        host = colony("Host", 1, food=60)
        caravan = Caravan(id=0, home=0, destination=1, legs=(), cargo={"food": 30.0})
        caravan.basis["food"] = basis
        struck: list[Haggle] = []
        do_business(caravan, host, colony("Home", 0), day=1, record=struck)
        settled.append(struck[0].price)

    assert settled[1] > settled[0]


def test_a_steward_can_put_its_own_negotiator_at_the_counter():
    """The seam milestone 4 needs, one level below prices: whatever argues for
    this colony sees the same table and writes through the same clamped move.
    """
    seen = []

    def stubborn(haggle: Haggle, side: str) -> Move:
        seen.append((haggle.good, side, haggle.turns(side)))
        return Move(side, COUNTER, price=haggle.seat(side).limit, qty=haggle.seat(side).want,
                    line="my price or no price.")

    host = colony("Host", 1, food=60)
    host_steward = Steward(host, negotiator=stubborn)
    caravan = Caravan(id=0, home=0, destination=1, legs=(), cargo={"food": 30.0})
    struck: list[Haggle] = []

    do_business(
        caravan,
        host,
        colony("Home", 0),
        day=1,
        speakers=Speakers(host=host_steward.speak),
        record=struck,
    )

    assert seen and all(side == HOST for _, side, _ in seen), "only its own side"
    # It never moves, so the trader's schedule is what closes the deal, at the
    # host's own limit -- a negotiator that will not budge gets its price.
    assert struck[0].settled
    assert struck[0].price == pytest.approx(host_steward.colony.price("food"), rel=0.5)


# ----------------------------------------------------------- in a whole world

def test_a_running_world_records_what_was_said_at_its_counters():
    sim = build_simulation(seed=23, settlements=3)
    sim.run(90)

    assert sim.negotiations, "three colonies for ninety days and nobody haggled"
    assert len(sim.negotiations) <= NEGOTIATIONS_KEPT, "the log has to be bounded"
    spoken = [haggle for haggle in sim.negotiations if haggle.transcript()]
    assert spoken, "a negotiation with nothing said is not a negotiation"
    assert any(haggle.settled for haggle in sim.negotiations)


def test_both_colonies_remember_a_negotiation_they_were_in():
    sim = build_simulation(seed=23, settlements=3)
    sim.run(90)

    remembered = [steward for steward in sim.stewards if steward.haggles]
    assert len(remembered) >= 2, "a deal has two sides and both should recall it"
    for steward in remembered:
        assert all(haggle.over for haggle in steward.haggles)
        assert steward.dealings()


def test_haggling_does_not_create_or_destroy_anything():
    """Conservation across a long run, with the price a decision throughout."""
    sim = build_simulation(seed=7, settlements=3)
    start, coin = sim.goods_in_world(), sim.coin_in_world()
    sim.run(120)
    end = sim.goods_in_world()

    for good in start:
        made = sim.produced.get(good, 0.0)
        used = sim.consumed.get(good, 0.0)
        lost = sim.lost.get(good, 0.0)
        assert end[good] == pytest.approx(start[good] + made - used - lost, abs=1e-6)
    assert sim.coin_in_world() == pytest.approx(coin - sim.escort_wages, abs=1e-6)


def test_a_haggling_world_still_replays_exactly():
    first = build_simulation(seed=11, settlements=3)
    first.run(60)
    again = build_simulation(seed=11, settlements=3)
    again.run(60)

    assert [h.summary() for h in first.negotiations] == [
        h.summary() for h in again.negotiations
    ]
    assert first.goods_in_world() == again.goods_in_world()


def test_the_viewer_shows_the_last_few_arguments():
    from colonysim.server import DEALS_SHOWN, negotiation_payload

    sim = build_simulation(seed=23, settlements=3)
    sim.run(90)
    shown = negotiation_payload(sim)

    assert 0 < len(shown) <= DEALS_SHOWN
    assert all("good" in deal and "said" in deal for deal in shown)
    assert any(deal["said"] for deal in shown)


def test_the_viewer_escapes_whatever_was_said():
    """The scripted negotiator only says what is in `negotiation.py`. The whole
    point of the seam is that something else may be doing the talking, and it
    should not be able to put markup on the page."""
    from colonysim.server import negotiation_payload

    sim = build_simulation(seed=23, settlements=3, stewards=False)
    haggle = table()
    haggle.play(Move(TRADER, OPEN, 2.0, 3.0, "<script>alert(1)</script>"))
    sim.negotiations.append(haggle)

    said = negotiation_payload(sim)[-1]["said"][-1][1]
    assert "<script>" not in said and "&lt;script&gt;" in said


# ------------------------------------------------------------- the adapter

def test_a_model_that_answers_with_a_line_can_do_the_talking():
    """`speaker_from` is the whole adapter: a prompt in, a line out. Nothing in
    this test touches the network, which is the point -- the seam is the same
    shape for a model, a player and a test double."""
    from colonysim.llm import speaker_from

    asked = []

    def fake(prompt: str) -> str:
        asked.append(prompt)
        return "COUNTER 2.75 6 two seventy-five, and I have walked all day."

    haggle = negotiate(table(), Speakers(trader=speaker_from(fake)))

    assert asked and "You are Cart" in asked[0]
    assert any("walked all day" in line for line in haggle.transcript())
    assert haggle.settled and haggle.price == pytest.approx(2.75)


def test_an_answer_nobody_can_read_falls_back_to_the_scripted_negotiator():
    """Every failure -- no key, no package, a timeout, an essay -- ends in the
    sim carrying on with a worse negotiator rather than stopping."""
    from colonysim.llm import speaker_from

    def useless(prompt: str) -> str:
        raise RuntimeError("no api key")

    haggle = negotiate(table(), Speakers(trader=speaker_from(useless)))
    scripted = negotiate(table())

    assert haggle.transcript() == scripted.transcript()


def test_the_adapter_reads_the_three_things_a_negotiator_can_say():
    from colonysim.llm import parse_move

    haggle = table()
    haggle.play(Move(TRADER, OPEN, 3.0, 5.0, "three."))

    assert parse_move("ACCEPT", haggle, HOST).act == ACCEPT
    assert parse_move("walk away", haggle, HOST).act == WALK
    counter = parse_move("COUNTER 2.20 4 we can find two twenty.", haggle, HOST)
    assert (counter.price, counter.qty) == (2.20, 4.0)
    assert counter.line == "we can find two twenty"
    assert parse_move("hmm", haggle, HOST) is None
    assert parse_move("", haggle, HOST) is None


def test_the_claude_adapter_stays_off_unless_it_is_switched_on(monkeypatch):
    """Importing the module changes nothing. Without the flag there is no call
    and no key is read, so the package stays dependency-free in practice as
    well as on paper."""
    from colonysim.llm import ENV_FLAG, claude_negotiator, enabled

    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert not enabled()

    haggle = negotiate(table(), Speakers(host=claude_negotiator()))
    assert haggle.transcript() == negotiate(table()).transcript()

    monkeypatch.setenv(ENV_FLAG, "1")
    assert enabled()
