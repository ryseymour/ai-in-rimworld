"""Storage, prices, currency, and a single trade."""
from __future__ import annotations

import pytest

from colonysim.goods import GOODS
from colonysim.money import SILVER, Currency, Purse
from colonysim.storage import MarketView, Storage
from colonysim.trade import (
    CAPACITY,
    Caravan,
    do_business,
    expected_relief,
    plan_cargo,
    settle,
)
from colonysim.simulation import build_colony
from colonysim.world import Settlement, World
from colonysim.terrain import generate_terrain
from colonysim.storage import Colony


def colony(name="A", cid=0, **stock) -> Colony:
    c = Colony(
        settlement=Settlement(cid, name, 5, 5),
        population=20,
        production={g: 0.0 for g in GOODS},
        consumption={"food": 10.0, "wood": 4.0, "stone": 2.0, "cloth": 1.0, "tools": 0.5},
        purse=Purse(SILVER, 500.0),
    )
    for good, qty in stock.items():
        c.storage.add(good, qty)
    return c


# ------------------------------------------------------------------ storage

def test_storage_never_goes_negative():
    s = Storage()
    s.add("food", 5)
    assert s.remove("food", 12) == 5
    assert s.get("food") == 0


def test_reserve_is_consumption_times_buffer_days():
    c = colony()
    assert c.reserve("food") == 10.0 * GOODS["food"].buffer_days


def test_only_stock_above_the_reserve_is_for_sale():
    c = colony(food=250)  # reserve is 200
    assert c.surplus("food") == pytest.approx(50)
    assert c.shortfall("food") == 0

    lean = colony(food=120)
    assert lean.surplus("food") == 0
    assert lean.shortfall("food") == pytest.approx(80)


def test_a_good_nobody_consumes_is_all_surplus():
    c = colony(food=10)
    c.consumption["tools"] = 0.0
    c.storage.add("tools", 7)
    assert c.reserve("tools") == 0
    assert c.surplus("tools") == 7


# ------------------------------------------------------------------- prices

def test_a_good_at_exactly_its_reserve_sells_for_base_price():
    c = colony(food=200)
    assert c.price("food") == pytest.approx(GOODS["food"].base_price)


def test_scarcity_raises_the_price_and_glut_lowers_it():
    scarce = colony(food=20)
    plenty = colony(food=900)
    assert scarce.price("food") > GOODS["food"].base_price
    assert plenty.price("food") < GOODS["food"].base_price


def test_price_is_clamped_at_both_ends():
    """A famine must not make one good worth more than a caravan, and a glut
    must not make one worthless."""
    empty = colony(food=0)
    flooded = colony(food=10_000_000)
    assert empty.price("food") == pytest.approx(GOODS["food"].base_price * 3.0)
    assert flooded.price("food") == pytest.approx(GOODS["food"].base_price * 0.35)


# ----------------------------------------------------------------- currency

def test_purse_pays_what_it_can_and_reports_it():
    p = Purse(SILVER, 10.0)
    assert p.withdraw(25.0) == 10.0
    assert p.amount == 0.0


def test_purse_transfer_conserves_coin():
    a, b = Purse(SILVER, 60.0), Purse(SILVER, 5.0)
    a.transfer_to(b, 25.0)
    assert (a.amount, b.amount) == (35.0, 30.0)


def test_purse_rejects_a_negative_balance():
    with pytest.raises(ValueError):
        Purse(SILVER, -1.0)
    with pytest.raises(ValueError):
        Purse(SILVER, 5.0).deposit(-3.0)


def test_currencies_do_not_mix_without_a_rate():
    with pytest.raises(ValueError):
        Purse(SILVER, 10.0).transfer_to(Purse(Currency("gold", "au", 12.0)), 5.0)


# --------------------------------------------------------------- settlement

def test_a_bill_is_paid_in_coin_when_there_is_coin():
    buyer = colony(food=400)
    seller_purse, cargo = Purse(SILVER), {}
    payment = settle(120.0, buyer, seller_purse, cargo)
    assert payment.coin == 120.0
    assert payment.goods == {}
    assert seller_purse.amount == 120.0


def test_what_coin_cannot_cover_is_paid_in_goods():
    """A colony rich in goods and poor in coin can still trade."""
    buyer = colony(food=900)
    buyer.purse = Purse(SILVER, 20.0)
    seller_purse, cargo = Purse(SILVER), {}

    payment = settle(200.0, buyer, seller_purse, cargo)

    assert payment.coin == 20.0
    assert payment.goods, "the rest of the bill should have been bartered"
    assert cargo == payment.goods, "bartered goods go into the seller's cargo"
    assert payment.goods_value == pytest.approx(180.0, rel=0.02)
    assert payment.total == pytest.approx(200.0, rel=0.02)


def test_barter_never_digs_into_the_reserve():
    buyer = colony(food=210)  # 10 above its reserve
    buyer.purse = Purse(SILVER, 0.0)
    settle(10_000.0, buyer, Purse(SILVER), {})
    assert buyer.storage.get("food") >= buyer.reserve("food") - 1e-6


# ------------------------------------------------------------------- cargo

def test_a_caravan_is_loaded_only_from_surplus():
    origin = colony(food=400)  # 200 spare
    market = MarketView.unvisited()
    cargo = plan_cargo(origin, market)
    assert cargo.get("food", 0) <= origin.surplus("food")


def test_nothing_is_loaded_that_the_destination_will_not_buy():
    """Carrying goods to a colony that is not short of them is a wasted trip."""
    origin = colony(food=900)
    market = MarketView.unvisited()
    full = MarketView(
        prices=market.prices,
        surplus=market.surplus,
        shortfall={good: 0.0 for good in GOODS},
        day=1,
    )
    assert plan_cargo(origin, full) == {}


def test_cargo_respects_capacity():
    origin = colony(food=10_000, wood=10_000, stone=10_000)
    cargo = plan_cargo(origin, MarketView.unvisited())
    load = sum(qty * GOODS[good].bulk for good, qty in cargo.items())
    assert load <= CAPACITY + 1e-6


def test_a_trip_is_not_worth_making_for_goods_the_seller_has_none_of():
    """The bug this guards: a market at exactly its reserve quotes an ordinary
    price while having nothing at all to sell."""
    buyer = colony(food=10)  # badly short
    at_reserve = MarketView(
        prices={good: GOODS[good].base_price for good in GOODS},
        surplus={good: 0.0 for good in GOODS},
        shortfall={good: 0.0 for good in GOODS},
        day=1,
    )
    assert expected_relief(buyer, at_reserve) == 0.0
    assert expected_relief(buyer, MarketView.unvisited()) > 0.0


# ------------------------------------------------------------------- trades

def test_one_trade_moves_goods_without_creating_any():
    seller = colony("Seller", 0, food=600)
    buyer = colony("Buyer", 1, food=40)
    caravan = Caravan(id=0, home=0, destination=1, legs=())
    caravan.cargo["food"] = seller.storage.remove("food", 300)
    seller.purse.transfer_to(caravan.purse, 200.0)

    before_goods = (
        seller.storage.get("food") + buyer.storage.get("food") + caravan.cargo.get("food", 0)
    )
    before_coin = seller.purse.amount + buyer.purse.amount + caravan.purse.amount

    do_business(caravan, buyer, seller, day=1)

    after_goods = (
        seller.storage.get("food") + buyer.storage.get("food") + caravan.cargo.get("food", 0)
    )
    after_coin = seller.purse.amount + buyer.purse.amount + caravan.purse.amount
    assert after_goods == pytest.approx(before_goods)
    assert after_coin == pytest.approx(before_coin)


def test_a_trade_leaves_the_buyer_better_stocked_and_the_seller_richer():
    seller = colony("Seller", 0, food=600)
    buyer = colony("Buyer", 1, food=40)
    caravan = Caravan(id=0, home=0, destination=1, legs=())
    caravan.cargo["food"] = seller.storage.remove("food", 300)

    do_business(caravan, buyer, seller, day=1)

    assert buyer.storage.get("food") > 40
    assert caravan.purse.amount > 0


def test_visiting_a_market_is_how_a_colony_learns_about_it():
    seller = colony("Seller", 0, food=600)
    buyer = colony("Buyer", 1, food=40)
    caravan = Caravan(id=0, home=0, destination=1, legs=())
    caravan.cargo["food"] = seller.storage.remove("food", 100)

    assert 1 not in seller.known
    do_business(caravan, buyer, seller, day=9)
    assert seller.known[1].day == 9
    assert seller.known[1].prices["food"] == pytest.approx(buyer.price("food"))


def test_colony_production_follows_the_land_around_it():
    terrain = generate_terrain(60, 40, 11)
    world = World(terrain, (Settlement(0, "A", 30, 20),))
    c = build_colony(world, world.settlements[0], population=20)
    assert sum(c.production.values()) > 0
