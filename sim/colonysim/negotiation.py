"""Haggling: how a price is actually agreed at the counter.

Up to here a sale has been an arithmetic fact. A caravan arrives, the host's
shelves say what the goods are worth, and that is the price -- nobody involved
has a say in it. This module makes the price the *outcome* of a short exchange
between two parties who each want something different out of it.

The shape of it is the oldest one there is. Each side has a price it will not
cross (the trader's is what the cargo was worth back home; the host's is the
most that good can fetch here), and a price it opens with, which is nowhere
near it. They take turns. Each turn, a side either takes what is on the table
or names a price a little closer to the other's. Whoever is in more of a hurry
gives ground faster, and so does worse out of it -- which is the whole reason
the dialogue is worth simulating rather than splitting the difference: a colony
four days from an empty granary pays more than one that is merely topping up,
and you can read why in what was said.

    * a deal is struck exactly when the two limits overlap, and never outside
      them, so no colony is ever talked into a price it could not live with;
    * if they do not overlap the goods stay on the cart and go home, which is
      a trip that did not pay -- the sim had no way to express that before;
    * `bargain` is the scripted negotiator. Pass anything with the same shape
      to `negotiate` (or hang it on a `Steward`) and that decides instead: a
      player, a rule nobody has written yet, or a model. `Haggle.brief` renders
      the table as prompt text for exactly that, and `Haggle.play` clamps
      whatever comes back, so a negotiator can say anything at all without
      putting the simulation into a state the rest of the code has to defend
      against.

That last part is the point of milestone 4: the dialogue is the seam, not the
decoration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .storage import clamp

#: Sides of the table. The trader is the one who walked here with the goods.
TRADER = "trader"
HOST = "host"

#: Acts a negotiator can take.
OPEN = "open"
COUNTER = "counter"
ACCEPT = "accept"
WALK = "walk"
ACTS = (OPEN, COUNTER, ACCEPT, WALK)

#: Turns each side gets before it must stand on its own limit. Short on
#: purpose: this is a cart in a village square, not a merger.
MAX_ROUNDS = 4
#: How far below its own idea of the price a host opens. The trader opens at
#: the most it could possibly get here, so this is the whole width of the
#: argument they then have.
OPENING_SPREAD = 0.22
#: Least of what it wants a host will still take at the very top of its range.
#: A price it does not like does not make it stop buying; it makes it buy less.
APPETITE_FLOOR = 0.45
#: Bounds on how stubborn a side can be. The exponent on its concession curve:
#: below 1 it gives ground early, above 1 it holds out and concedes late.
MIN_PATIENCE = 0.5
MAX_PATIENCE = 2.0
#: Longest line a negotiator may say. An agent that returns an essay gets the
#: first sentence of it.
MAX_LINE = 160


def other(side: str) -> str:
    return HOST if side == TRADER else TRADER


@dataclass(frozen=True)
class Move:
    """One thing said at the table, and what it commits the speaker to."""

    speaker: str
    act: str
    #: The price per unit this move puts on the table. On an accept it is the
    #: price being accepted, which is the *other* side's.
    price: float
    #: Units at that price. A host that dislikes the price takes less of it.
    qty: float
    line: str = ""

    @property
    def priced(self) -> bool:
        """Whether this move leaves an offer standing for the other side."""
        return self.act in (OPEN, COUNTER)


@dataclass(frozen=True)
class Seat:
    """One side's private position: what it wants, and what it will not cross.

    `limit` is the price it walks away rather than cross; `aspiration` is where
    it opens, which is always on the good side of that limit. `eagerness` is
    how badly it needs the deal, and the only thing that differs between two
    otherwise identical negotiators -- it decides how fast the gap between
    those two numbers is given away.
    """

    side: str
    name: str
    limit: float
    aspiration: float
    want: float
    #: What this side privately thinks the good is worth, for what it says.
    quote: float = 0.0
    eagerness: float = 0.5

    @property
    def patience(self) -> float:
        """The exponent on the concession curve.

        A desperate side (eagerness 1) is at 0.5 and has given away most of its
        room by its second turn; a comfortable one (eagerness 0) is at 2.0 and
        holds near its opening until the last moment.
        """
        return clamp(
            2.0 ** (1.0 - 2.0 * clamp(self.eagerness, 0.0, 1.0)),
            MIN_PATIENCE,
            MAX_PATIENCE,
        )

    @property
    def opening(self) -> float:
        """Where it starts, which is never worse for it than where it stops.

        A seat built with an aspiration on the wrong side of its own limit has
        nothing to argue with, so it opens on the limit and stands there. That
        is a real position -- take it or leave it -- and it is the one thing
        that must not become an offer below the limit on the first turn.
        """
        return self.aspiration if self.prefers(self.aspiration, self.limit) else self.limit

    def position(self, turn: int, rounds: int) -> float:
        """Where this seat stands on its `turn`-th move.

        Walks from the opening to the limit over `rounds` turns, so by the last
        turn every negotiator is standing on its own limit and the thing
        terminates whether or not anyone is feeling generous.
        """
        if rounds <= 0:
            return self.limit
        start = self.opening
        share = clamp(turn / rounds, 0.0, 1.0) ** self.patience
        return start + (self.limit - start) * share

    def prefers(self, price: float, to: float) -> bool:
        """Whether `price` is at least as good for this seat as `to`."""
        return price >= to if self.side == TRADER else price <= to

    def appetite(self, price: float) -> float:
        """How much it will take at that price.

        Only the buyer really has one: a host asked more than it thinks the
        good is worth buys less of it, unless it is short enough that it has to
        take whatever it can get. The seller always wants to sell the lot.
        """
        if self.side == TRADER or self.limit <= self.quote:
            return self.want
        over = clamp((price - self.quote) / (self.limit - self.quote), 0.0, 1.0)
        trim = (1.0 - APPETITE_FLOOR) * over * (1.0 - clamp(self.eagerness, 0.0, 1.0))
        return self.want * (1.0 - trim)


@dataclass
class Haggle:
    """One negotiation over one good, as it unfolds.

    Holds the two seats, everything said so far, and -- once it is over -- what
    was agreed. Nothing here touches storage or purses: a `Haggle` is a
    conversation about a price, and `trade.do_business` is what acts on it.
    """

    good: str
    day: int
    trader: Seat
    host: Seat
    rounds: int = MAX_ROUNDS
    moves: list[Move] = field(default_factory=list)
    #: The agreed price per unit, or None while it is open or if it failed.
    price: float | None = None
    qty: float = 0.0
    closed: str = ""

    # ----------------------------------------------------------- reading
    @property
    def over(self) -> bool:
        return bool(self.closed)

    @property
    def settled(self) -> bool:
        return self.price is not None

    @property
    def value(self) -> float:
        return (self.price or 0.0) * self.qty

    def seat(self, side: str) -> Seat:
        return self.trader if side == TRADER else self.host

    def standing(self, side: str) -> Move | None:
        """That side's offer as it stands, or None if it has not spoken."""
        for move in reversed(self.moves):
            if move.speaker == side and move.priced:
                return move
        return None

    def turns(self, side: str) -> int:
        """How many priced moves that side has made."""
        return sum(1 for move in self.moves if move.speaker == side and move.priced)

    def position(self, side: str) -> float:
        seat = self.seat(side)
        return seat.position(self.turns(side), self.rounds)

    # ----------------------------------------------------------- writing
    def play(self, move: Move) -> Move:
        """Take a negotiator's move, make it safe, and put it on the record.

        Everything a negotiator can get wrong is fixed here rather than
        defended against everywhere else: an unknown act becomes a counter, a
        price becomes a number inside the range anyone at this table could
        mean, a quantity cannot exceed what is actually on the cart, and an
        accept always means the terms the other side actually offered rather
        than terms the accepter made up while accepting.
        """
        speaker = move.speaker if move.speaker in (TRADER, HOST) else TRADER
        theirs = self.standing(other(speaker))
        act = move.act if move.act in ACTS else COUNTER
        line = " ".join(str(move.line).split())[:MAX_LINE]

        if act == ACCEPT and theirs is None:
            # Nothing has been offered yet, so there is nothing to accept.
            act = OPEN
        if act == ACCEPT:
            safe = Move(speaker, ACCEPT, theirs.price, theirs.qty, line)
        elif act == WALK:
            safe = Move(speaker, WALK, self.position(speaker), 0.0, line)
        else:
            ceiling = max(
                self.trader.aspiration, self.trader.limit,
                self.host.aspiration, self.host.limit,
            )
            price = clamp(float(move.price), 0.0, max(ceiling, 0.0))
            qty = clamp(float(move.qty), 0.0, min(self.trader.want, self.host.want))
            safe = Move(speaker, act, price, qty, line)

        self.moves.append(safe)
        if safe.act == ACCEPT:
            self.price, self.qty, self.closed = safe.price, safe.qty, ACCEPT
        elif safe.act == WALK:
            self.price, self.qty, self.closed = None, 0.0, WALK
        return safe

    # ----------------------------------------------------------- telling
    def transcript(self) -> list[str]:
        """What was said, as a reader would see it."""
        return [
            f"{self.seat(move.speaker).name}: {move.line}"
            for move in self.moves
            if move.line
        ]

    def summary(self) -> str:
        if self.settled:
            return (
                f"{self.host.name} took {self.qty:.0f} {self.good} from "
                f"{self.trader.name} at {self.price:.2f}"
            )
        return f"no deal on {self.good} between {self.trader.name} and {self.host.name}"

    def brief(self, side: str) -> str:
        """The table as prompt text, for whoever is deciding next.

        Deliberately the same facts `bargain` reasons over rather than a
        summary of them, so a model handed this is choosing from what the
        scripted negotiator had, not less.
        """
        seat, them = self.seat(side), self.seat(other(side))
        selling = "selling" if side == TRADER else "buying"
        lines = [
            f"You are {seat.name}, {selling} {seat.want:.0f} {self.good} "
            f"to {them.name} on day {self.day}."
            if side == TRADER
            else f"You are {seat.name}, buying up to {seat.want:.0f} {self.good} "
            f"from {them.name} on day {self.day}.",
            f"You think it is worth {seat.quote:.2f} a unit."
            if seat.quote
            else "You have no firm idea what it is worth.",
            f"You will not go {'below' if side == TRADER else 'above'} "
            f"{seat.limit:.2f} a unit; you would rather walk away.",
            f"This is turn {self.turns(side) + 1} of {self.rounds}. "
            f"On the last turn you must stand on your limit or leave.",
        ]
        theirs = self.standing(other(side))
        if theirs is None:
            lines.append("Nothing has been offered yet. Open.")
        else:
            lines.append(
                f"{them.name} is offering {theirs.qty:.0f} at {theirs.price:.2f}."
            )
        if self.moves:
            lines.append("So far:")
            lines.extend(f"  {said}" for said in self.transcript())
        lines.append(
            "Answer with one line: ACCEPT, or WALK, or a price and a quantity "
            "and what you say, as `COUNTER <price> <qty> <what you say>`."
        )
        return "\n".join(lines)


#: What decides a move. The scripted `bargain` below is the default; anything
#: with this shape can take its place.
Speaker = Callable[[Haggle, str], Move]


@dataclass(frozen=True)
class Speakers:
    """Who is talking on each side of one negotiation."""

    trader: Speaker | None = None
    host: Speaker | None = None

    def of(self, side: str) -> Speaker:
        chosen = self.trader if side == TRADER else self.host
        return chosen or bargain


# --------------------------------------------------------------- the scripted one


def bargain(haggle: Haggle, side: str) -> Move:
    """The default negotiator: concede on a schedule, and take a good offer.

    Three rules, in order. Take what is on the table if it is at least as good
    as what you were about to ask for -- which is what makes an eager side pay
    up, because eagerness is exactly what makes your own next ask worse. Leave
    once both of you are standing on your limits and they still have not met,
    because nothing either of you can say after that changes the arithmetic --
    never before the other side has had its last turn, or you would be walking
    out on an offer it was about to make. Otherwise name your next price, and
    say why.
    """
    seat = haggle.seat(side)
    turn = haggle.turns(side)
    position = seat.position(turn, haggle.rounds)
    theirs = haggle.standing(other(side))

    if theirs is not None and seat.prefers(theirs.price, position):
        return Move(side, ACCEPT, theirs.price, theirs.qty, _accepting(haggle, side, theirs))
    spent = turn >= haggle.rounds and haggle.turns(other(side)) >= haggle.rounds
    if theirs is not None and spent:
        return Move(side, WALK, position, 0.0, _leaving(haggle, side, theirs))

    act = OPEN if turn == 0 else COUNTER
    qty = seat.appetite(position)
    return Move(side, act, position, qty, _offering(haggle, side, position, qty, act))


# --------------------------------------------------------------- what gets said

#: Lines are picked by the day and the good rather than at random, so a world
#: replays word for word. Each one still has to be true of the move it goes
#: with, which is why they are grouped by what the move actually is.
_OPENINGS = {
    TRADER: (
        "{qty:.0f} {good}, straight off the road. {price:.2f} the unit.",
        "I have {qty:.0f} {good} on the cart. {price:.2f} and it is yours.",
        "{good} at {price:.2f}. You will not see another cart this week.",
    ),
    HOST: (
        "We can find {price:.2f} for {good}, no more. {qty:.0f} of it.",
        "{price:.2f} the unit for {qty:.0f}. That is what the store will bear.",
        "Say {price:.2f} and we will take {qty:.0f} off you.",
    ),
}
_HARD = {
    TRADER: (
        "{price:.2f}. I walked a long road for this.",
        "{price:.2f}, and that is me being reasonable.",
        "Come up. {price:.2f} the unit.",
    ),
    HOST: (
        "{price:.2f}, and not a coin over.",
        "We are not desperate. {price:.2f} for {qty:.0f}.",
        "{price:.2f}. Try the next village if you like.",
    ),
}
_SOFT = {
    TRADER: (
        "{price:.2f}, then. I would rather not cart it home.",
        "Take it at {price:.2f} and we are done.",
        "{price:.2f}. That is close to what it cost me.",
    ),
    HOST: (
        "{price:.2f}. We need it, and you know we need it.",
        "{price:.2f} for {qty:.0f}, and we will not haggle further.",
        "Our shelves are bare. {price:.2f}.",
    ),
}
_ACCEPTS = (
    "Done. {qty:.0f} at {price:.2f}.",
    "Agreed -- {qty:.0f} {good} at {price:.2f}.",
    "That will do. {price:.2f}.",
)
_WALKS = {
    TRADER: (
        "Not at {price:.2f}. It goes home with me.",
        "No. It is worth more to my own people than that.",
    ),
    HOST: (
        "Then keep it. We will do without.",
        "No sale. {price:.2f} is beyond us.",
    ),
}


def _pick(lines: tuple[str, ...], haggle: Haggle, side: str) -> str:
    """Deterministic variety: the same table always says the same thing."""
    seed = haggle.day + len(haggle.good) + len(haggle.moves) + (side == HOST)
    return lines[seed % len(lines)]


def _offering(haggle: Haggle, side: str, price: float, qty: float, act: str) -> str:
    seat = haggle.seat(side)
    if act == OPEN:
        lines = _OPENINGS[side]
    else:
        lines = _SOFT[side] if seat.eagerness >= 0.5 else _HARD[side]
    return _pick(lines, haggle, side).format(price=price, qty=qty, good=haggle.good)


def _accepting(haggle: Haggle, side: str, theirs: Move) -> str:
    return _pick(_ACCEPTS, haggle, side).format(
        price=theirs.price, qty=theirs.qty, good=haggle.good
    )


def _leaving(haggle: Haggle, side: str, theirs: Move) -> str:
    return _pick(_WALKS[side], haggle, side).format(
        price=theirs.price, qty=theirs.qty, good=haggle.good
    )


# --------------------------------------------------------------- running one


def negotiate(
    haggle: Haggle, speakers: Speakers | None = None, opener: str = TRADER
) -> Haggle:
    """Run the exchange to its end and return the same `Haggle`, closed.

    The trader speaks first because it is the one who turned up. The loop is
    hard-bounded whatever the negotiators do: if nobody has accepted or left by
    the time both sides have had their turns, the deal simply did not happen.
    """
    speakers = speakers or Speakers()
    side = opener if opener in (TRADER, HOST) else TRADER
    # Enough for both sides to reach their limits and one of them to say so.
    limit = 2 * (haggle.rounds + 1) + 2
    while not haggle.over and len(haggle.moves) < limit:
        haggle.play(speakers.of(side)(haggle, side))
        side = other(side)
    if not haggle.over:
        haggle.closed = WALK
    return haggle
