"""Traders: what they carry, where they go, and how a deal is settled.

A trade is priced in currency. The buyer pays from its purse as far as the
purse goes, and covers whatever is left by handing back goods of its own at its
own prices -- so a colony that is coin-poor but goods-rich can still trade, and
the barter it hands over becomes the caravan's return load.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .goods import GOODS
from .money import SILVER, Purse
from .roads import RoadNetwork, Route, travel_cost
from .storage import MAX_MULT, Colony, MarketView
from .terrain import Terrain
from .wildlife import Encounter

#: Cargo space in one caravan.
CAPACITY = 120.0
#: Cost units a caravan covers in a day.
TRAVEL_PER_DAY = 22.0
#: A trader only bothers when the price gap clears this much per unit.
MIN_MARGIN = 0.15
#: Most coin a caravan sets out with, to buy on arrival before it has sold.
#: It never takes more than a share of the purse, so a colony cannot send its
#: whole treasury down the road in one go.
FLOAT = 400.0
FLOAT_SHARE = 0.6
#: Below this a colony cannot fund a buying trip at all.
MIN_TRIP_COIN = 40.0
#: A journey has to be worth making. Without this, caravans set out for the
#: sake of a coin's worth of stone and the roads fill with pointless traffic.
MIN_TRIP_WORTH = 25.0
#: How much of a caravan's space is left empty on a road that is certain to be
#: attacked. A trader on a bad road walks light: less to lose and less to slow
#: it down. At the usual hazards this trims a load by a tenth or so.
LOAD_CAUTION = 0.5
#: The most a caravan will add to a host's own price for having carried the
#: goods through dangerous country, as a share of that price. A host short of
#: the good pays it; nobody pays above the usual price ceiling.
MAX_RISK_PREMIUM = 0.35

OUTBOUND = "outbound"
TRADING = "trading"
RETURNING = "returning"
HOME = "home"


@dataclass
class Caravan:
    id: int
    home: int
    destination: int
    #: The chain of roads to the destination. More than one leg when the
    #: destination is not a direct neighbour.
    legs: tuple[Route, ...]
    cargo: dict[str, float] = field(default_factory=dict)
    purse: Purse = field(default_factory=lambda: Purse(SILVER))
    state: str = OUTBOUND
    days_left: float = 0.0
    #: Chance of meeting something on the road over one leg of this journey,
    #: read off the wilds at dispatch. Drives the load, the premium it asks,
    #: and whether it took guards.
    hazard: float = 0.0
    escorted: bool = False
    #: Everything that happened to it on the road.
    encounters: list[Encounter] = field(default_factory=list)
    #: The day it set out, so a caravan that never gets home is detectable.
    dispatched_day: int = 0
    #: Filled in on arrival, so the thread can show what actually happened.
    ledger: list[str] = field(default_factory=list)

    @property
    def load(self) -> float:
        return sum(qty * GOODS[good].bulk for good, qty in self.cargo.items())

    @property
    def risk_premium(self) -> float:
        """What it asks above a host's own price for having got there at all.

        A caravan that walked a wolf road wants paying for it. The host only
        wears that while it is short of the good, and never above the price
        ceiling, so the premium shows up as a thin margin on dangerous routes
        rather than as a colony being gouged."""
        return min(MAX_RISK_PREMIUM, self.hazard * MAX_RISK_PREMIUM * 2.0)


def travel_days(
    terrain: Terrain, network: RoadNetwork, legs: tuple[Route, ...]
) -> float:
    """How long a journey takes, given the roads as they stand today.

    Road tier feeds straight into this, so a route that gets used becomes a
    faster route, which makes it more attractive, which wears it further.
    """
    cost = sum(travel_cost(terrain, network, leg.path) for leg in legs)
    return max(1.0, math.ceil(cost / TRAVEL_PER_DAY))


def cautious_capacity(hazard: float, capacity: float = CAPACITY) -> float:
    """How full a caravan is willing to load for a road of this hazard.

    The response to risk that costs nothing and always helps: put less on the
    road. It does not change the chance of being caught, only what is there to
    be taken when it happens."""
    return capacity * (1.0 - LOAD_CAUTION * max(0.0, min(1.0, hazard)))


def plan_cargo(
    origin: Colony, market: MarketView, capacity: float = CAPACITY
) -> dict[str, float]:
    """Fill a caravan out of the origin's surplus, best margin per unit of
    cargo space first.

    Only surplus is ever loaded, so selling abroad can never leave a colony
    short at home; and no more is loaded than the destination was last seen to
    be short of, since anything beyond that will not sell when it arrives.
    """
    candidates = []
    for good, spec in GOODS.items():
        available = min(origin.surplus(good), market.shortfall.get(good, 0.0))
        if available <= 0:
            continue
        margin = market.prices.get(good, spec.base_price) - origin.price(good)
        if margin < MIN_MARGIN:
            continue
        candidates.append((margin / spec.bulk, good, available))
    candidates.sort(reverse=True)

    cargo: dict[str, float] = {}
    space = capacity
    for _, good, available in candidates:
        if space <= 0:
            break
        qty = min(available, space / GOODS[good].bulk)
        if qty > 0:
            cargo[good] = qty
            space -= qty * GOODS[good].bulk
    return cargo


def expected_profit(
    origin: Colony, market: MarketView, cargo: dict[str, float]
) -> float:
    """What the outbound cargo is expected to earn."""
    return sum(
        qty * (market.prices.get(good, GOODS[good].base_price) - origin.price(good))
        for good, qty in cargo.items()
    )


def expected_relief(origin: Colony, market: MarketView) -> float:
    """What the trip is worth for what it brings back.

    A colony short of everything has no cargo to sell, so profit alone would
    keep it at home starving with a full purse. Covering its own shortfall with
    goods that are cheaper elsewhere is worth exactly the same price gap, so it
    counts alongside profit when deciding whether to send anyone out.
    """
    budget = origin.purse.amount
    relief = 0.0
    for good in sorted(GOODS):
        want = min(origin.shortfall(good), market.surplus.get(good, 0.0))
        there = market.prices.get(good, GOODS[good].base_price)
        here = origin.price(good)
        if want <= 0 or there <= 0 or there >= here:
            continue
        qty = min(want, budget / there)
        relief += qty * (here - there)
        budget -= qty * there
        if budget <= 0:
            break
    return relief


def trip_float(colony: Colony) -> float:
    """Coin to send with a caravan."""
    return min(colony.purse.amount * FLOAT_SHARE, FLOAT)


@dataclass(frozen=True)
class Payment:
    """How a bill was actually settled."""

    coin: float
    goods: dict[str, float]
    goods_value: float
    bill: float = 0.0

    @property
    def total(self) -> float:
        return self.coin + self.goods_value

    @property
    def shortfall(self) -> float:
        """What the buyer could cover with neither coin nor goods."""
        return max(0.0, self.bill - self.total)


def settle(
    bill: float, buyer: Colony, seller_purse: Purse, seller_cargo: dict[str, float]
) -> Payment:
    """Pay a bill in coin, then in goods for whatever coin would not cover.

    Bartered goods come out of the buyer's surplus only, so settling a debt can
    never eat into what a colony is holding back for itself. Each parcel is
    valued at the price at the moment it changes hands -- handing over food
    makes the buyer's remaining food dearer, and the next parcel reflects that.
    """
    paid = buyer.purse.transfer_to(seller_purse, bill)
    owed = round(bill - paid, 6)
    bartered: dict[str, float] = {}
    value = 0.0
    if owed <= 0.01:
        return Payment(coin=paid, goods=bartered, goods_value=0.0, bill=bill)

    # Cheapest surplus first: a colony pays its debts with what it can spare.
    offers = sorted(
        ((buyer.price(good), good) for good in GOODS if buyer.surplus(good) > 0),
        key=lambda pair: (pair[0], pair[1]),
    )
    for _, good in offers:
        if owed <= 0.01:
            break
        price = buyer.price(good)
        if price <= 0:
            continue
        qty = buyer.storage.remove(good, min(buyer.surplus(good), owed / price))
        if qty <= 0:
            continue
        bartered[good] = bartered.get(good, 0.0) + qty
        seller_cargo[good] = seller_cargo.get(good, 0.0) + qty
        value += qty * price
        owed = round(bill - paid - value, 6)

    return Payment(coin=paid, goods=bartered, goods_value=value, bill=bill)


def do_business(caravan: Caravan, host: Colony, home: Colony, day: int = 0) -> None:
    """The caravan sells what it brought, then buys what home is short of."""
    sold_value = 0.0
    premium = caravan.risk_premium
    for good in sorted(caravan.cargo):
        qty = min(caravan.cargo[good], host.shortfall(good))
        if qty <= 0:
            continue
        # Quoted before the goods land and move the price, plus whatever the
        # road was worth, capped at what any good can fetch here.
        ceiling = GOODS[good].base_price * MAX_MULT
        price = min(host.price(good) * (1.0 + premium), ceiling)
        bill = qty * price

        caravan.cargo[good] -= qty
        if caravan.cargo[good] <= 1e-9:
            del caravan.cargo[good]
        host.storage.add(good, qty)

        payment = settle(bill, host, caravan.purse, caravan.cargo)
        sold_value += payment.total
        note = f"sold {qty:.0f} {good} for {payment.coin:.0f} coin"
        if payment.goods:
            note += " and " + ", ".join(
                f"{q:.0f} {g}" for g, q in sorted(payment.goods.items())
            )
        caravan.ledger.append(note)

    for good in sorted(GOODS):
        want = home.shortfall(good) - caravan.cargo.get(good, 0.0)
        spare = host.surplus(good)
        if want <= 0 or spare <= 0:
            continue
        price = host.price(good)
        affordable = caravan.purse.amount / price if price > 0 else 0.0
        # Coming home is the same road, so the same caution applies to the
        # return load as to the outbound one.
        room = cautious_capacity(caravan.hazard) - caravan.load
        space = room / GOODS[good].bulk
        qty = min(want, spare, affordable, space)
        if qty <= 0.01:
            continue
        qty = host.storage.remove(good, qty)
        caravan.cargo[good] = caravan.cargo.get(good, 0.0) + qty
        caravan.purse.transfer_to(host.purse, qty * price)
        caravan.ledger.append(f"bought {qty:.0f} {good} for {qty * price:.0f} coin")

    # The trip is also how the home colony learns what this market looks like.
    home.known[host.id] = host.market_view(day)
    caravan.ledger.append(f"turnover {sold_value:.0f} coin at {host.name}")


def unload(caravan: Caravan, home: Colony) -> None:
    for good, qty in list(caravan.cargo.items()):
        home.storage.add(good, qty)
        del caravan.cargo[good]
    caravan.purse.transfer_to(home.purse, caravan.purse.amount)
    caravan.state = HOME
