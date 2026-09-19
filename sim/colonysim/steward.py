"""The steward: a colony's own agent, and its hands on the trade network.

Everything before this file is mechanism -- land makes goods, scarcity makes
prices, caravans move things between the two. Nothing in it decides anything.
The steward is the one who does: it can see the roads, what its neighbours were
last seen to have and charge, and where its own caravans are, and it can change
three things about its colony.

    * what it charges -- a markup on what scarcity alone would ask, which is
      both what a visiting caravan pays here and what this colony pays for
      imports, so the decision has a real cost either way;
    * what it holds back -- the reserve, which is the line between what is for
      sale and what the colony wants to buy;
    * where its people work -- a lean on the land's own output, conserved, so
      supply can answer a price instead of being fixed by terrain forever.

`merchant` is the scripted steward: it bids up what it is short of, undercuts
whoever else could supply the buyer it wants, and moves labour toward what the
region is paying for. Swap it for anything with the same shape -- a player, or
a model call once a week -- by passing `decide` to `Steward`. That is milestone
4 of the design, and this is the seam it plugs into.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .goods import GOOD_NAMES, GOODS
from .roads import RoadNetwork, Route
from .storage import (
    MAX_MARKUP,
    MIN_MARKUP,
    Colony,
    MarketView,
    clamp,
)
from .trade import Caravan

#: A colony is "short" below this much of its own buffer, and "glutted" above
#: the other. Between them it leaves its prices alone and lets them drift back
#: to what scarcity says, which is what stops a stance outliving its reason.
SHORT_COVER = 0.9
GLUT_COVER = 1.6
#: How fast a stance moves toward where the steward wants it. Prices that jump
#: on one day's stock make traders chase noise; this takes about a week to
#: cross the band, which is roughly a caravan's round trip.
ADJUST_RATE = 0.34
#: Margin a foreign trader has to see before hauling a good here, plus what it
#: wants for the risk. A steward bidding for imports has to clear it, so this
#: is the one number it works its price back from.
IMPORT_MARGIN = 0.25
RISK_MARGIN = 0.5
#: How far under a rival's price the colony puts itself when both could supply
#: the same buyer. Small on purpose: undercutting is worth doing, and worth
#: doing by as little as possible.
UNDERCUT = 0.96
#: Most a steward will bid up when nobody it knows of has any to sell. There is
#: no point paying a premium into an empty region.
BLIND_RAISE = 0.25
#: Below this much coin a colony cannot really bid for anything, so it stops
#: pretending it can and keeps its prices near the plain ones.
LOW_COIN = 120.0
#: Weight on a long-running average of cover, which is what the slow decisions
#: -- the reserve and where people work -- are made on. One bad week should
#: not move a village's fields.
MEMORY = 0.88
#: How often the slow decisions are revisited. Prices move daily; people and
#: granaries do not.
SLOW_INTERVAL = 7
#: How hard a steward leans the land toward what is scarce and what sells.
FOCUS_STEP = 0.45
#: Lines of reasoning kept. Enough to see why a colony is doing what it is
#: doing, not enough to grow without bound over a long run.
LOG_LINES = 40


@dataclass(frozen=True)
class Link:
    """One other colony, as its neighbour's steward sees it.

    The road is live -- its length and its danger are today's -- but the market
    is a memory from the last caravan that came back, which is the whole reason
    stewards can be wrong.
    """

    colony: int
    name: str
    #: One-way travel, in days, over the best chain of roads today.
    days: float
    #: Chance of meeting something on the way, on one leg of the journey.
    hazard: float
    #: Mean road tier along the way: 0 is open country, 3 is paved.
    tier: float
    legs: tuple[Route, ...]
    market: MarketView

    @property
    def visited(self) -> bool:
        return self.market.day >= 0

    def age(self, day: int) -> int:
        """Days since anyone actually looked, or -1 for never.

        A large age means the steward is deciding on old news, which is where
        its worse decisions come from.
        """
        return day - self.market.day if self.visited else -1

    def price(self, good: str) -> float:
        return self.market.prices.get(good, GOODS[good].base_price)

    def surplus(self, good: str) -> float:
        return self.market.surplus.get(good, 0.0)

    def shortfall(self, good: str) -> float:
        return self.market.shortfall.get(good, 0.0)


@dataclass(frozen=True)
class NetworkView:
    """Everything a steward can see of the trade network on one day.

    Built fresh each review from the simulation, so a steward never holds a
    reference to the world and cannot reach past what this exposes. That is
    what makes the same object safe to hand to an agent.
    """

    day: int
    home: int
    links: dict[int, Link]
    #: This colony's own caravans, out on the road right now. A steward does
    #: not get to see anyone else's: what other colonies are up to it learns
    #: the same way a trader does, by arriving and looking.
    caravans: tuple[Caravan, ...] = ()

    def neighbours(self) -> list[Link]:
        """Everyone reachable, nearest first."""
        return sorted(self.links.values(), key=lambda link: (link.days, link.colony))

    def sellers(self, good: str) -> list[Link]:
        """Who was last seen with some to spare, cheapest first."""
        return sorted(
            (link for link in self.links.values() if link.surplus(good) > 0),
            key=lambda link: (link.price(good), link.colony),
        )

    def buyers(self, good: str) -> list[Link]:
        """Who was last seen short of it, deepest need first."""
        return sorted(
            (link for link in self.links.values() if link.shortfall(good) > 0),
            key=lambda link: (-link.shortfall(good), link.colony),
        )

    def rivals(self, good: str, buyer: int) -> list[Link]:
        """Everyone else who could supply that buyer with this good.

        The reason a price is a decision and not a readout: a colony with wood
        to sell and one buyer for it is bidding against whoever else has wood.
        """
        return [
            link
            for link in self.sellers(good)
            if link.colony != buyer and link.surplus(good) > 0
        ]

    def cheapest(self, good: str) -> Link | None:
        sellers = self.sellers(good)
        return sellers[0] if sellers else None

    def dearest(self, good: str) -> Link | None:
        buyers = [link for link in self.links.values() if link.shortfall(good) > 0]
        return max(buyers, key=lambda link: (link.price(good), -link.colony), default=None)


@dataclass
class Steward:
    """The colony's trader-in-chief.

    Reading is free and always current for the roads, always stale for other
    markets. Writing goes through these methods rather than at the policy
    directly, so every change is clamped, smoothed and written down.
    """

    colony: Colony
    #: What makes the decisions. `None` is the scripted merchant below; anything
    #: with the same shape can take its place, including something that thinks
    #: for a second and a half and charges by the token.
    decide: Callable[["Steward", NetworkView], None] | None = None
    #: The last thing it was shown, kept so a UI (or an agent's next prompt)
    #: can ask what the steward was looking at when it decided.
    view: NetworkView | None = None
    log: list[str] = field(default_factory=list)
    reviews: int = 0
    #: A slow average of how well covered each good has been, which is what the
    #: reserve and the labour decisions are made on.
    memory: dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------- reading
    @property
    def name(self) -> str:
        return self.colony.name

    @property
    def coin(self) -> float:
        return self.colony.purse.amount

    def stock(self, good: str) -> float:
        return self.colony.storage.get(good)

    def price(self, good: str) -> float:
        """What the colony is quoting today, stance included."""
        return self.colony.price(good)

    def cover(self, good: str) -> float:
        """Stock as a fraction of the good's own buffer.

        Measured against the good's buffer rather than the colony's current
        reserve on purpose: a steward that judged itself by a reserve it had
        just raised would talk itself into raising it again.
        """
        days = GOODS[good].buffer_days
        rate = self.colony.consumption.get(good, 0.0)
        if rate <= 0 or days <= 0:
            return float("inf")
        return self.stock(good) / (rate * days)

    def days_of_stock(self, good: str) -> float:
        rate = self.colony.consumption.get(good, 0.0)
        return self.stock(good) / rate if rate else float("inf")

    def remembered(self, good: str) -> float:
        return self.memory.get(good, self.cover(good))

    def stance(self) -> dict[str, dict[str, float]]:
        """Everything this steward has changed about its colony."""
        return self.colony.policy.adjustments()

    # ------------------------------------------------------------- writing
    def set_markup(self, good: str, value: float, why: str = "") -> float:
        """Put this colony's price at `value` times what scarcity would ask."""
        before = self.colony.policy.markup_for(good)
        after = self.colony.policy.set_markup(good, value)
        if abs(after - before) > 0.02 and why:
            self.note(f"{good} at {after:.2f}x -- {why}")
        return after

    def nudge_markup(self, good: str, toward: float, why: str = "") -> float:
        """Move part of the way to a price rather than jumping to it."""
        before = self.colony.policy.markup_for(good)
        return self.set_markup(good, before + ADJUST_RATE * (toward - before), why)

    def set_reserve_days(self, good: str, days: float, why: str = "") -> float:
        """Keep back this many days of the good. Returns the days actually set."""
        buffer_days = GOODS[good].buffer_days
        if buffer_days <= 0:
            return 0.0
        before = self.colony.reserve_days(good)
        self.colony.policy.set_reserve(good, days / buffer_days)
        after = self.colony.reserve_days(good)
        if abs(after - before) > 0.5 and why:
            self.note(f"holding {after:.0f} days of {good} -- {why}")
        return after

    def set_focus(self, good: str, weight: float) -> None:
        """Lean the colony's work toward or away from a good.

        Rebalanced against every other good immediately, so the colony's total
        output at ordinary prices never changes: this moves people between
        jobs, it does not conjure them.
        """
        self.colony.policy.set_focus(good, weight)
        self.colony.policy.rebalance_focus(self.colony.labour_shares())

    def clear(self) -> None:
        """Drop every adjustment and trade on scarcity alone again."""
        self.colony.policy.markup.clear()
        self.colony.policy.reserve_mult.clear()
        self.colony.policy.focus.clear()

    def note(self, line: str) -> None:
        day = self.view.day if self.view else 0
        self.log.append(f"day {day}: {line}")
        del self.log[:-LOG_LINES]

    # ------------------------------------------------------------- deciding
    def review(self, view: NetworkView) -> None:
        """One look at the network, and whatever the steward makes of it."""
        self.view = view
        self.reviews += 1
        for good in GOOD_NAMES:
            cover = self.cover(good)
            if cover == float("inf"):
                continue
            remembered = self.memory.get(good, cover)
            self.memory[good] = MEMORY * remembered + (1.0 - MEMORY) * cover
        (self.decide or merchant)(self, view)

    def brief(self) -> str:
        """The steward's own situation, in words, for whoever decides next.

        Written for a prompt as much as for a person: it is the whole of what
        the scripted merchant below reasons over, so an agent handed this text
        is choosing from the same facts rather than a summary of them.
        """
        view = self.view
        lines = [
            f"{self.name}, day {view.day if view else 0}. "
            f"{self.coin:.0f} coin, {self.colony.population} people."
        ]
        lines.append("what we hold:")
        for good in GOOD_NAMES:
            cover = self.cover(good)
            state = "short" if cover < SHORT_COVER else "spare" if cover > GLUT_COVER else "steady"
            lines.append(
                f"  {good:<6} {self.stock(good):>7.0f}  "
                f"{self.days_of_stock(good):>5.0f} days  {state:<6} "
                f"asking {self.price(good):.2f} ({self.colony.policy.markup_for(good):.2f}x)"
            )
        if view:
            lines.append("who we can reach:")
            for link in view.neighbours():
                age = link.age(view.day)
                seen = f"seen {age}d ago" if age >= 0 else "never visited"
                lines.append(
                    f"  {link.name:<12} {link.days:>3.0f} days, "
                    f"hazard {link.hazard:.0%}, {seen}"
                )
                for good in GOOD_NAMES:
                    if link.surplus(good) > 1 or link.shortfall(good) > 1:
                        side = "spare" if link.surplus(good) > 1 else "wants"
                        qty = max(link.surplus(good), link.shortfall(good))
                        lines.append(
                            f"      {good:<6} {side} {qty:>6.0f} at {link.price(good):.2f}"
                        )
            if view.caravans:
                lines.append("our caravans:")
                for caravan in view.caravans:
                    where = view.links.get(caravan.destination)
                    lines.append(
                        f"  {caravan.state} to "
                        f"{where.name if where else caravan.destination}, "
                        f"{caravan.days_left:.0f} days out"
                    )
        return "\n".join(lines)


# ------------------------------------------------------------- the scripted one


def merchant(steward: Steward, view: NetworkView) -> None:
    """The default steward: keep the colony supplied, and sell into the gap.

    Two moves, and they are opposites of each other, which is what makes the
    stance mean anything. Short of something, it raises its price until a
    foreign trader can see a margin in bringing it -- and pays that price
    itself when the caravan lands. Sitting on a pile of something, it cuts its
    price under whoever else could supply the colony that wants it -- and takes
    less per unit for doing so. Everything else follows those two.
    """
    for good in GOOD_NAMES:
        _price(steward, view, good)

    if steward.reviews % SLOW_INTERVAL == 0:
        for good in GOOD_NAMES:
            _reserve(steward, good)
        _labour(steward, view)


def _price(steward: Steward, view: NetworkView, good: str) -> None:
    cover = steward.cover(good)
    if cover == float("inf"):
        return
    scarcity = steward.colony.scarcity_price(good)
    if scarcity <= 0:
        return

    if cover < SHORT_COVER:
        target = _bid_for_supply(steward, view, good, scarcity, cover)
        why = "short, bidding for a caravan"
    elif cover > GLUT_COVER:
        target = _cut_to_sell(steward, view, good, scarcity, cover)
        why = "sitting on a pile, cutting to shift it"
    else:
        # Nothing to say about this good today, so the stance goes back to
        # ordinary rather than outliving the reason it was taken.
        target = 1.0
        why = ""

    steward.nudge_markup(good, target, why)


def _bid_for_supply(
    steward: Steward, view: NetworkView, good: str, scarcity: float, cover: float
) -> float:
    """What we would have to charge for someone to bother bringing us some.

    Worked backwards from the trader's own sum: a caravan loads a good when the
    price here beats the price at home by enough to be worth the road. So the
    steward looks up the cheapest place it knows that has any to spare, adds
    the margin a trader wants and what the road is worth, and asks for that.
    """
    sellers = view.sellers(good)
    if not sellers:
        # Nobody within reach is known to have any. Bidding hard into an empty
        # region only means overpaying if someone does turn up.
        return 1.0 + BLIND_RAISE * (SHORT_COVER - cover)

    source = sellers[0]
    wanted = source.price(good) * (
        1.0 + IMPORT_MARGIN + RISK_MARGIN * source.hazard
    )
    target = max(1.0, wanted / scarcity)

    if steward.coin < LOW_COIN:
        # A colony this poor pays in barter, and barter comes out of the same
        # shelves it is trying to fill. Bidding is for colonies with coin.
        target = min(target, 1.1)
    return min(target, MAX_MARKUP)


def _cut_to_sell(
    steward: Steward, view: NetworkView, good: str, scarcity: float, cover: float
) -> float:
    """How far under the going rate to go to be the one who sells it.

    A discount deep enough to move the pile, and then, if somebody else could
    supply the colony that wants it, deep enough to be the cheaper of the two.
    Both of those cost real coin per unit, which is why neither is unlimited.
    """
    glut = 1.0 - 0.3 * (cover - GLUT_COVER)

    buyers = view.buyers(good)
    if buyers:
        rivals = view.rivals(good, buyers[0].colony)
        if rivals:
            under = min(rival.price(good) for rival in rivals) * UNDERCUT
            glut = min(glut, under / scarcity)
    return max(MIN_MARKUP, min(glut, 1.0))


def _reserve(steward: Steward, good: str) -> None:
    """How much to keep back, judged on months rather than days.

    A colony that has been scraping along on a good all season wants a deeper
    granary, which also stops it selling the little it has; one that has been
    drowning in it can safely call more of it surplus and put it on the road.
    """
    remembered = steward.remembered(good)
    if remembered == float("inf"):
        return
    buffer_days = GOODS[good].buffer_days

    if remembered < 0.7:
        target = 1.0 + 1.2 * (0.7 - remembered)
        why = "we keep running it down"
    elif remembered > 2.0:
        target = 1.0 - 0.3 * (remembered - 2.0)
        why = "more than we can use"
    else:
        target = 1.0
        why = ""

    current = steward.colony.policy.reserve_for(good)
    moved = current + ADJUST_RATE * (target - current)
    steward.set_reserve_days(good, moved * buffer_days, why)


def _labour(steward: Steward, view: NetworkView) -> None:
    """Move people toward what the colony lacks and the region pays for.

    This is the loop that makes the thing an economy rather than a delivery
    service: a price that stays high long enough stops being a reason to buy
    and starts being a reason to make. Terrain still decides what a village is
    any good at, so a forest that leans into stone gets very little for it.
    """
    colony = steward.colony
    shares = colony.labour_shares()
    if sum(shares.values()) <= 0:
        return

    for good in GOOD_NAMES:
        remembered = steward.remembered(good)
        if remembered == float("inf"):
            continue
        scarce = 1.0 - clamp(remembered, 0.3, 2.0)

        abroad = [
            link.price(good) / GOODS[good].base_price
            for link in view.links.values()
            if link.shortfall(good) > 0
        ]
        demand = max(abroad) - 1.0 if abroad else 0.0

        target = 1.0 + FOCUS_STEP * (scarce + 0.5 * demand)
        current = colony.policy.focus_for(good)
        colony.policy.set_focus(good, current + ADJUST_RATE * (target - current))

    colony.policy.rebalance_focus(shares)

    leaning = {
        good: round(colony.policy.focus_for(good), 2)
        for good in GOOD_NAMES
        if abs(colony.policy.focus_for(good) - 1.0) > 0.05
    }
    if leaning:
        steward.note(
            "work moved: "
            + ", ".join(f"{good} {weight:.2f}x" for good, weight in sorted(leaning.items()))
        )


def route_tier(network: RoadNetwork, legs: tuple[Route, ...]) -> float:
    """Mean road tier along a journey: how good the way there actually is."""
    tiles = [tile for leg in legs for tile in leg.path]
    if not tiles:
        return 0.0
    return sum(
        network.tiles[tile].tier if tile in network.tiles else 0 for tile in tiles
    ) / len(tiles)
