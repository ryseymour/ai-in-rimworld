"""What colonies think of each other, and what it costs them.

Every colony keeps one number about every other colony it has dealt with: how
it reckons that colony behaves at the counter. Nothing sets that number
directly. It is written by conduct -- what a caravan charged, whether a bill
was covered, whether anyone was turned away at the gate -- and it is read back
by the same trade code that produced it, so a colony that cheats is buying
today's margin with tomorrow's prices.

The number runs from -1 (shunned) through 0 (strangers, and where everyone
starts) to +1 (trusted). Four things read it:

    * **the price at the counter** -- a colony pays a well-regarded caravan
      better than its own asking price and haggles a badly-regarded one down,
      both ways round, so standing is worth coin per unit on every deal;
    * **where caravans go** -- a colony steers its one caravan toward the
      partners it thinks well of, because that is where the prices are better;
    * **guards** -- two colonies that trust each other share an escort down the
      road they both use, and the wage is split;
    * **whether there is a deal at all** -- below `EMBARGO` a colony turns the
      caravan away at the gate, and the colony that was turned away thinks a
      little less of it for that.

It decays toward neutral every day, slowly. That is what makes the punishment
lasting rather than permanent: a colony that gouged its way through a hard
winter is still paying for it a season later, and can still work its way back.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

#: The ends of the scale, and where two colonies that have never met stand.
WORST = -1.0
NEUTRAL = 0.0
BEST = 1.0

#: Share of the remaining standing that falls away each day. At this rate half
#: of a grudge is still there eight months later, which is the "lasting" part:
#: a colony that gouged its way through one winter is still paying worse
#: prices the following autumn, and still has a way back if it behaves.
DECAY = 0.003

#: The coin value at which a deal counts for its full weight. A parcel this
#: size is a good day's trading between two villages.
DEAL_SIZE = 25.0

#: How far above a host's own asking price a caravan can go before it reads as
#: gouging rather than as a fair price for a hard road, and the overcharge at
#: which it is gouging as hard as it possibly could be.
GOUGE_TOLERANCE = 0.08
GOUGE_FULL = 0.35

#: What a full-sized deal is worth to standing, by how it was conducted.
#: Gouging is worth several fair deals, and deliberately so: reputation is
#: something to protect rather than an average to shrug at. It still takes a
#: pattern of it to close a gate, not one bad afternoon.
FAIR_GAIN = 0.08
GOUGE_LOSS = 0.25
#: An unpaid bill is the lightest of the three on purpose. A colony here only
#: fails to cover one when it has run out of coin *and* has nothing above its
#: reserve to hand over -- which makes it broke, not dishonest, and this sim
#: cannot tell a colony that would not pay from one that could not. So an
#: unpaid bill is a credit mark: it makes a colony a worse customer, at worse
#: prices and with fewer visits, and on its own it does not close a gate.
#: Starving the poorest village for being poor is not what this is for.
SHORT_LOSS = 0.12
#: Being turned away at the gate. Small per refusal on purpose: an embargo
#: should sour a relationship over weeks, not start a feud in one morning.
REFUSAL_LOSS = 0.06

#: How far standing moves the price at the counter, at either end of the scale.
PRICE_SWING = 0.15
#: How much the expected worth of a trip moves with what the colony thinks of
#: the place it would be trading with. It is not a bonus: better-regarded
#: partners really do pay better, and this is the trader expecting that.
BIAS_SWING = 0.40
#: Standing at which two colonies will share an escort, and the most that can
#: come off the wage when they do.
FRIENDLY = 0.30
GUARD_SHARE = 0.30
#: Below this a colony will not deal at all.
EMBARGO = -0.55

#: Remarks kept per colony. Enough to see why a neighbour is unwelcome, not
#: enough to grow without bound over a long run.
REMARK_LINES = 40


def clamp(value: float, low: float = WORST, high: float = BEST) -> float:
    return max(low, min(high, value))


def deal_weight(value: float) -> float:
    """How much a deal of this size counts toward an opinion.

    Square-rooted rather than straight: what a colony remembers is mostly who
    it has been dealing with, and only partly how much. A parcel a tenth the
    size of a full day's trade is a third of the impression, not a tenth of
    one, and nothing beyond a full day's trade counts for more.
    """
    return min(1.0, math.sqrt(max(value, 0.0) / DEAL_SIZE))


def describe(standing: float) -> str:
    """The standing in a word, for a panel or a steward's brief."""
    if standing <= EMBARGO:
        return "shunned"
    if standing < -0.2:
        return "wary"
    if standing < 0.2:
        return "neutral"
    if standing < 0.55:
        return "friendly"
    return "trusted"


def favour(standing: float) -> float:
    """The multiplier a colony puts on its own price for this partner.

    Above 1 for a colony it trusts and below 1 for one it does not, and it
    applies to both sides of the counter: a trusted caravan is paid more than
    the asking price for what it brought, and charged less than it for what it
    takes home. Goodwill is the cheaper supplier, which is the whole point.
    """
    return 1.0 + PRICE_SWING * clamp(standing)


def trades_with(standing: float) -> bool:
    return standing > EMBARGO


def trade_bias(standing: float) -> float:
    """How much more (or less) a trip to this colony looks worth."""
    return 1.0 + BIAS_SWING * clamp(standing)


def guard_discount(standing: float) -> float:
    """Share off an escort's wage for a road two colonies both use.

    Guards are shared, not given: it takes goodwill at both ends, so the
    caller passes the lower of the two standings.
    """
    if standing <= FRIENDLY:
        return 0.0
    return GUARD_SHARE * min(1.0, (standing - FRIENDLY) / (BEST - FRIENDLY))


@dataclass(frozen=True)
class Remark:
    """One thing a colony noticed about another, and what it cost them."""

    day: int
    about: int
    name: str
    kind: str
    change: float
    detail: str

    def describe(self) -> str:
        sign = "+" if self.change >= 0 else ""
        return f"day {self.day}: {self.name} {self.detail} ({sign}{self.change:.2f})"


@dataclass
class Reputation:
    """One colony's opinion of every other colony it has dealt with.

    Scores are only written through `record`, so every change is clamped and
    written down with its reason. Anything that has never been dealt with is
    simply absent, which reads as neutral.
    """

    scores: dict[int, float] = field(default_factory=dict)
    remarks: list[Remark] = field(default_factory=list)
    #: Off leaves every colony a permanent stranger to every other: no opinion
    #: is ever written, so every read is neutral and the trade code behaves
    #: exactly as it did before anyone kept score. The control case for every
    #: claim about what reputation does.
    enabled: bool = True

    # ------------------------------------------------------------- reading
    def of(self, colony_id: int) -> float:
        return self.scores.get(colony_id, NEUTRAL)

    def word_for(self, colony_id: int) -> str:
        return describe(self.of(colony_id))

    def trades_with(self, colony_id: int) -> bool:
        return trades_with(self.of(colony_id))

    def favour(self, colony_id: int) -> float:
        return favour(self.of(colony_id))

    def known(self) -> dict[int, float]:
        """Everyone this colony has an opinion about, worst first."""
        return dict(sorted(self.scores.items(), key=lambda pair: (pair[1], pair[0])))

    def about(self, colony_id: int) -> list[Remark]:
        return [remark for remark in self.remarks if remark.about == colony_id]

    # ------------------------------------------------------------- writing
    def record(
        self,
        day: int,
        about: int,
        name: str,
        kind: str,
        change: float,
        detail: str,
    ) -> float:
        """Move an opinion, and remember why. Returns the standing after."""
        if change == 0.0 or not self.enabled:
            return self.of(about)
        after = clamp(self.of(about) + change)
        moved = after - self.of(about)
        self.scores[about] = after
        self.remarks.append(
            Remark(day=day, about=about, name=name, kind=kind, change=moved, detail=detail)
        )
        del self.remarks[:-REMARK_LINES]
        return after

    def decay(self, rate: float | None = None) -> None:
        """Let every opinion drift back toward neutral by a day's worth.

        Silent: drifting back is not conduct and nobody remarks on it. Scores
        that have essentially arrived at neutral are dropped, so a colony's
        opinions are the ones it actually holds.
        """
        rate = DECAY if rate is None else rate
        for other, standing in list(self.scores.items()):
            faded = standing * (1.0 - rate)
            if abs(faded) < 0.005:
                del self.scores[other]
            else:
                self.scores[other] = faded

    # ------------------------------------------------------------- judging
    def judge_deal(
        self, day: int, about: int, name: str, paid: float, honest: float
    ) -> float:
        """What the host makes of a parcel it has just bought.

        `honest` is what the host itself would have asked for the same goods;
        `paid` is what it actually handed over. A caravan that sells at the
        host's own price is doing what it said it would do and is thought a
        little better of for it. One that adds a premium the host can see --
        for the road, for the wolves, for the fact that the host is desperate
        -- is thought worse of in proportion to how big the premium was and how
        much of the colony's coin went with it.
        """
        if honest <= 0.0 or paid <= 0.0:
            return self.of(about)
        weight = deal_weight(max(paid, honest))
        over = paid / honest - 1.0
        if over > GOUGE_TOLERANCE:
            hard = min(1.0, (over - GOUGE_TOLERANCE) / GOUGE_FULL)
            return self.record(
                day,
                about,
                name,
                "gouged",
                -GOUGE_LOSS * weight * hard,
                f"charged {over:.0%} over our own price",
            )
        return self.record(
            day, about, name, "fair", FAIR_GAIN * weight, "dealt at our own price"
        )

    def judge_payment(
        self, day: int, about: int, name: str, bill: float, shortfall: float
    ) -> float:
        """What a seller makes of a bill that was not covered.

        A buyer out of coin settles the rest in goods off its own shelves; a
        buyer out of both walks away owing, and the trader carries that home.
        A bill covered in full is the opposite and is worth saying so: most of
        the goodwill in this world is made of ordinary bills paid on the day.
        """
        if bill <= 0.0:
            return self.of(about)
        weight = deal_weight(bill)
        if shortfall <= 0.01:
            return self.record(
                day, about, name, "paid", FAIR_GAIN * weight, "covered the bill"
            )
        short = min(1.0, shortfall / bill)
        return self.record(
            day,
            about,
            name,
            "short",
            -SHORT_LOSS * weight * short,
            f"left {shortfall:.0f} coin of {bill:.0f} unpaid",
        )

    def judge_purchase(self, day: int, about: int, name: str, spent: float) -> float:
        """Coin over the counter the other way: a caravan buying what it came
        for, at the asking price.

        There is nothing to complain about in a purchase -- the buyer picked
        the price by choosing to buy -- so both sides simply think a little
        better of a colony they have done ordinary business with. It is the
        slow half of the system: relationships built by turning up, paying and
        going home again, which is what the sharp losses are measured against.
        """
        if spent <= 0.0:
            return self.of(about)
        return self.record(
            day,
            about,
            name,
            "custom",
            FAIR_GAIN * deal_weight(spent),
            f"good custom, {spent:.0f} coin over the counter",
        )

    def refused(self, day: int, about: int, name: str) -> float:
        """What a colony makes of being turned away at someone's gate."""
        return self.record(
            day, about, name, "refused", -REFUSAL_LOSS, "turned our caravan away"
        )
