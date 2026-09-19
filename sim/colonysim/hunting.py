"""Hunting: the deer and boar a colony lives off, and what it costs to take them.

Game animals are not a rate attached to a colony. They live on the map, in
herds, the same way the wolves and bears of `wildlife.py` live in dens, and a
colony hunts whatever happens to graze within a day's walk of it. Everything
else here follows from that:

* **Where the game is** comes from the land. Deer want the forest and the open
  plains, boar want the forest and the broken ground above it, and unlike a
  predator's den a herd will happily graze up to a village's fields -- game is
  a reason to settle somewhere, not a reason to avoid it.
* **What a party brings home** is its arrows, times what it is carrying, times
  how good its ground is. Arrows are the effort; bows are what turns effort
  into meat; the herds decide whether there was anything out there to shoot.
* **Hunting thins the herds it works.** A party that takes more than the ground
  grows back walks further every season for less, until it stops. That is what
  stops hunting being a second farm with no ceiling.
* **The wild is out there too.** Hunters are off the roads by definition, so
  the danger field in `wildlife.py` reaches them at its full strength, with no
  road tier to divide it down and no guards to hire. A colony's own weapons are
  all that answer for it.

What comes back is `food` and `cloth` -- meat and hides -- which are ordinary
goods, so a hunt feeds the population, fills the granary a neighbour is short
of, and puts hides in a caravan without anything else in the sim being told.

The point of the whole loop is that it is a second way to be fed, and one that
belongs to the land a colony sits on rather than to the road that reaches it. A
forest village with a fletcher turns wood into meat without waiting for a
caravan, which is exactly the independence a weapon is for; it is a supplement
to the fields rather than a replacement, so a village that cannot farm still
cannot live on hunting alone.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .crafting import armed_strength
from .wildlife import Wilds, deterrence
from .world import World

if TYPE_CHECKING:  # pragma: no cover - import for types only
    from .storage import Colony

Point = tuple[int, int]

#: Arrows loosed per head per day, and the share of a colony ordinarily out
#: hunting. Set so a hunting party shoots a month's worth of arrows in about a
#: month, which is what makes arrows a running demand rather than a one-off
#: purchase.
ARROWS_PER_CAPITA = 0.07
HUNTER_SHARE = 0.2

#: What a party with no bow between them recovers, as a share of what an armed
#: one does. Snares and thrown spears are not nothing; they are not a bow.
BOWLESS_TAKE = 0.31

#: How far the take follows the size of the party. More hands find more of what
#: was shot, drive more of it towards the shooters and carry more of it home --
#: but less each time, the same way more hands on the same land do in
#: `people.LAND_ELASTICITY`.
RECOVERY_ELASTICITY = 0.7

#: A hand in the woods is a hand out of the fields, one for one. This is the
#: whole cost of sending more people hunting, and it is why a colony on good
#: farmland never bothers: it would be giving up more than it brought back.
FIELD_PULL = 1.0


@dataclass(frozen=True)
class Game:
    """One kind of animal worth hunting.

    `arrows_each` is how many arrows it takes to bring one down, which is what
    makes a boar a worse bargain than a deer for all that there is more of it.
    `peril` is the chance per animal that it turns on the party first.
    """

    name: str
    #: Relative chance of a herd living on each kind of ground.
    habitat: dict[str, float]
    #: How far from its ground a herd ranges, and so how far off it can be hunted.
    roam: float
    arrows_each: float
    #: What one animal is worth on the shelves: meat as `food`, hide as `cloth`.
    meat: float
    hides: float
    peril: float
    glyph: str


DEER = Game(
    name="deer",
    habitat={"forest": 1.0, "plains": 0.9, "rough": 0.3, "water": 0.0},
    roam=8.0,
    arrows_each=3.0,
    meat=2.4,
    hides=0.36,
    peril=0.0,
    glyph="d",
)
BOAR = Game(
    name="boar",
    habitat={"forest": 1.0, "rough": 0.7, "plains": 0.35, "water": 0.0},
    roam=6.0,
    arrows_each=4.0,
    meat=3.0,
    hides=0.40,
    peril=0.015,
    glyph="b",
)
GAME = {g.name: g for g in (DEER, BOAR)}

#: Herds per tile of map: about ninety on the default 90x45 world, which puts
#: a handful within reach of most villages and none at all within reach of a
#: few. Game is the one resource a colony cannot decide to have.
HERD_DENSITY = 0.022
#: How far a party will walk from home and still be back by dark.
HUNT_RANGE = 9.0
#: Herd weight within reach that counts as ordinary country. Ground is measured
#: against it, so a middling colony hunts at 1.0 and the yields above are what
#: an arrow is worth there.
TYPICAL_GROUND = 2.0
#: How much of a herd at the far edge of a party's range still counts. Not
#: nothing: the party walks to it, which is what a day out is for.
EDGE_SHARE = 0.35
#: The best any ground gets. Rich country is worth hunting; it is not worth
#: abandoning the fields for.
MAX_ABUNDANCE = 1.4

#: What one animal taken costs the herd it came from, and how fast a herd
#: closes the gap back to full. Growth is proportional to what is missing, so a
#: steady take settles a herd at `1 - take/HERD_REGROWTH` rather than pinning
#: it at either end: ordinary hunting leaves a herd a little thinner than it
#: found it, a colony with one herd in reach empties it, and country nobody
#: works is back to full in a season.
THINNING = 0.18
HERD_REGROWTH = 0.02

#: How much of the danger field a party out in it all day actually runs into.
#: A caravan crosses a tile; hunters spend the day in the tile, off any road.
PARTY_EXPOSURE = 8.0
MAX_HUNT_DANGER = 0.5
#: What a predator takes off a party it finds, and the chance somebody does not
#: walk home from it. Rare on purpose: the wild's cost is mostly a lost day.
PREDATOR_TOLL = 0.7
MAULING = 0.15
#: How much of that a colony's own weapons answer for. Not all of it: a party
#: that meets a bear in the trees is on its own whatever it is carrying, which
#: is the difference between the woods and the road, where guards can be hired.
ARMS_COVER = 0.7


# --------------------------------------------------------------- the animals


@dataclass
class Herd:
    """Deer or boar on a patch of ground. `strength` is 0..1 and moves: hunting
    takes it down, a season of being left alone puts it back."""

    id: int
    species: str
    x: int
    y: int
    strength: float = 1.0

    @property
    def kind(self) -> Game:
        return GAME[self.species]

    @property
    def pos(self) -> Point:
        return (self.x, self.y)


@dataclass(frozen=True)
class HuntingGround:
    """The country one colony's hunters work, as it is today.

    `abundance` is 1.0 on ordinary ground and 0.0 where there is nothing left
    to shoot. `mix` is what is out there, which decides what comes home. The
    rest is what else the party might meet.
    """

    abundance: float = 1.0
    mix: dict[str, float] = field(default_factory=lambda: {DEER.name: 1.0})
    danger: float = 0.0
    predator: str = ""
    #: The herds the party works, so what it takes can be taken off them.
    herds: tuple[int, ...] = ()

    @property
    def empty(self) -> bool:
        return self.abundance <= 0.0 or not self.mix

    def describe(self) -> str:
        if self.empty:
            return "hunted out"
        what = ", ".join(sorted(self.mix))
        word = "rich" if self.abundance > 1.1 else (
            "thin" if self.abundance < 0.6 else "fair"
        )
        out = f"{word} hunting ({what})"
        if self.danger > 0.05:
            out += f", {self.predator} about"
        return out


def open_country() -> HuntingGround:
    """The ground a colony hunts when nobody has said where it is.

    Ordinary country, deer and boar on it, nothing else about. It is what a
    `Colony` on its own hunts and what the sim did before the herds were on the
    map, which is what makes a world with no game in it a control case rather
    than a broken one.
    """
    return HuntingGround(
        abundance=1.0,
        mix={DEER.name: 0.6, BOAR.name: 0.4},
        danger=0.0,
    )


def _falloff(distance: float, reach: float) -> float:
    """How much a herd this far off counts towards a colony's hunting."""
    if reach <= 0.0:
        return 0.0
    near = 1.0 - max(0.0, min(1.0, distance / reach))
    return EDGE_SHARE + (1.0 - EDGE_SHARE) * near


def _predator_at(wilds: Wilds, x: int, y: int) -> str:
    """Whatever is likeliest to be met on this patch of ground.

    Only for saying so afterwards -- the chance of meeting anything is the
    whole danger field, not this one den -- but a hunt that says "wolves" is
    worth more to a reader than one that says "an animal".
    """
    best = 0.0
    name = ""
    for den in wilds.dens:
        if den.strength <= 0.0:
            continue
        kind = den.kind
        distance = math.hypot(x - den.x, y - den.y)
        if distance >= kind.reach:
            continue
        weight = kind.boldness * den.strength * (1.0 - distance / kind.reach) ** 2
        if weight > best:
            best, name = weight, kind.name
    return name


@dataclass
class Herds:
    """Every herd on the map, and the hunting each colony gets out of them."""

    herds: tuple[Herd, ...] = ()

    def near(self, x: int, y: int, radius: float = HUNT_RANGE) -> list[Herd]:
        """Herds a party out of here could reach, whatever is left of them."""
        return [
            herd
            for herd in self.herds
            if herd.strength > 0.0
            and math.hypot(x - herd.x, y - herd.y) <= min(radius, herd.kind.roam)
        ]

    def weight_at(self, x: int, y: int, radius: float = HUNT_RANGE) -> float:
        """Raw herd weight in reach: strength, nearer herds counting for more."""
        total = 0.0
        for herd in self.near(x, y, radius):
            distance = math.hypot(x - herd.x, y - herd.y)
            reach = min(radius, herd.kind.roam)
            total += herd.strength * _falloff(distance, reach) if reach else 0.0
        return total

    def ground(
        self, x: int, y: int, wilds: Wilds | None = None, radius: float = HUNT_RANGE
    ) -> HuntingGround:
        """What a party setting out from here has to work with today."""
        reachable = self.near(x, y, radius)
        if not reachable:
            return HuntingGround(abundance=0.0, mix={}, danger=0.0)

        shares: dict[str, float] = {}
        danger = 0.0
        weight = 0.0
        worst = 0.0
        predator = ""
        for herd in reachable:
            distance = math.hypot(x - herd.x, y - herd.y)
            reach = min(radius, herd.kind.roam)
            here = herd.strength * _falloff(distance, reach) if reach else 0.0
            if here <= 0.0:
                continue
            shares[herd.species] = shares.get(herd.species, 0.0) + here
            weight += here
            if wilds is not None:
                at_herd = wilds.danger_at(herd.x, herd.y)
                danger += at_herd * here
                if at_herd > worst:
                    worst = at_herd
                    predator = _predator_at(wilds, herd.x, herd.y) or predator
        if weight <= 0.0:
            return HuntingGround(abundance=0.0, mix={}, danger=0.0)

        return HuntingGround(
            abundance=min(MAX_ABUNDANCE, weight / TYPICAL_GROUND),
            mix={species: share / weight for species, share in shares.items()},
            danger=min(MAX_HUNT_DANGER, PARTY_EXPOSURE * danger / weight),
            predator=predator,
            herds=tuple(herd.id for herd in reachable),
        )

    def thin(self, ground: HuntingGround, taken: dict[str, float]) -> None:
        """Take what was shot off the herds it was shot out of.

        Spread over every herd of that species the party could reach, because
        the party walks to whichever one it finds: a colony with one herd in
        reach empties it, and one with five hunts the same number of animals
        for years without anything noticing.
        """
        worked = set(ground.herds)
        for species, animals in taken.items():
            if animals <= 0.0:
                continue
            herds = [
                herd
                for herd in self.herds
                if herd.id in worked and herd.species == species
            ]
            if not herds:
                continue
            loss = THINNING * animals / len(herds)
            for herd in herds:
                herd.strength = max(0.0, herd.strength - loss)

    def graze_day(self) -> None:
        """A day passes for the game: every herd closes on full again.

        Proportional to what is missing, so a herd that was left alone last
        season is already back and one that was shot out is still not.
        """
        for herd in self.herds:
            herd.strength = min(
                1.0, herd.strength + HERD_REGROWTH * (1.0 - herd.strength)
            )

    def tally(self) -> dict[str, int]:
        return {
            species: sum(1 for herd in self.herds if herd.species == species)
            for species in sorted(GAME)
        }


def populate(world: World, seed: int, density: float = HERD_DENSITY) -> Herds:
    """Scatter herds over a world's terrain.

    The same rejection sampling the dens use, minus the exclusion around
    villages: deer graze the edge of a field, which is why a colony has any
    hunting at all and why the hunting it has is a property of its own ground
    rather than of the roads that leave it.
    """
    terrain = world.terrain
    rng = random.Random(seed ^ 0x6A3E)
    target = max(0, round(terrain.width * terrain.height * density))

    herds: list[Herd] = []
    attempts = 0
    while len(herds) < target and attempts < target * 200:
        attempts += 1
        x = rng.randrange(terrain.width)
        y = rng.randrange(terrain.height)
        kind_name = terrain.kind(x, y)
        suitability = {g.name: g.habitat.get(kind_name, 0.0) for g in GAME.values()}
        total = sum(suitability.values())
        if total <= 0.0 or rng.random() > max(suitability.values()):
            continue
        roll = rng.random() * total
        species = DEER.name
        for name, weight in sorted(suitability.items()):
            roll -= weight
            if roll <= 0.0:
                species = name
                break
        herds.append(Herd(len(herds), species, x, y))

    return Herds(tuple(herds))


# ------------------------------------------------------------- who goes out


def party_share(colony: "Colony") -> float:
    """The share of the colony out hunting, after its steward has had a say."""
    return HUNTER_SHARE * colony.policy.hunt_share()


def hunters(colony: "Colony") -> float:
    return max(0.0, colony.population * party_share(colony))


def field_hands(colony: "Colony") -> float:
    """What the land makes with the people it has left.

    1.0 when the usual share is in the woods, less when more are. This is the
    other half of the hunting dial: a steward that sends a third of the village
    out after deer is deciding to harvest less of everything else, and the
    arithmetic says so rather than the balance being a matter of opinion.
    """
    return max(0.3, 1.0 - FIELD_PULL * (party_share(colony) - HUNTER_SHARE))


def bow_coverage(colony: "Colony") -> float:
    """The share of the hunting party that has a bow to hunt with."""
    party = hunters(colony)
    if party <= 0.0:
        return 0.0
    return max(0.0, min(1.0, colony.storage.get("bow") / party))


def shooting(colony: "Colony") -> float:
    """What the party's arrows are worth, 0..1, on what it is carrying."""
    return BOWLESS_TAKE + (1.0 - BOWLESS_TAKE) * bow_coverage(colony)


def recovery(colony: "Colony") -> float:
    """How much of what is shot the party actually brings home, against the
    ordinary party's 1.0."""
    share = party_share(colony)
    if share <= 0.0:
        return 0.0
    return (share / HUNTER_SHARE) ** RECOVERY_ELASTICITY


def meat_per_arrow(colony: "Colony", ground: HuntingGround | None = None) -> float:
    """Food off one arrow here today. The number the whole loop comes down to."""
    ground = ground or open_country()
    if ground.empty:
        return 0.0
    per_arrow = sum(
        share * GAME[species].meat / GAME[species].arrows_each
        for species, share in ground.mix.items()
    )
    return per_arrow * shooting(colony) * recovery(colony) * ground.abundance


# ------------------------------------------------------------------ the hunt


@dataclass(frozen=True)
class Hunt:
    """One day's hunting party: who went out, and what came back."""

    day: int
    colony: str
    party: float
    bows: float
    arrows: float
    ground: float
    #: Animals brought down, by species.
    taken: dict[str, float] = field(default_factory=dict)
    #: What that was worth on the shelves, after anything that went wrong.
    bag: dict[str, float] = field(default_factory=dict)
    #: "", or what went wrong: "wolves", "bears", or "boar".
    mishap: str = ""
    #: What a predator took off them, and whoever did not walk home.
    dropped: dict[str, float] = field(default_factory=dict)
    hurt: float = 0.0

    @property
    def animals(self) -> float:
        return sum(self.taken.values())

    def describe(self) -> str:
        """One line for the log and the viewer.

        Animals come with a decimal because a day's party brings home part of
        a carcass on average, the same way a colony eats fractions of a field:
        everything in this sim is a rate, and rounding a deer to nothing would
        make an ordinary day's hunting look like a failure.
        """
        out = f"{self.colony}: {self.party:.0f} out"
        out += f" with {self.bows:.0%} bows" if self.bows > 0 else " barehanded"
        took = ", ".join(
            f"{qty:.1f} {species}"
            for species, qty in sorted(self.taken.items())
            if qty >= 0.05
        )
        food = self.bag.get("food", 0.0)
        if took:
            out += f", took {took}"
            if food > 0.0:
                out += f" for {food:.1f} food"
        elif food > 0.0:
            out += f", {food:.1f} food home"
        else:
            out += ", nothing home"
        if self.mishap == "boar":
            out += "; a boar turned on them"
        elif self.mishap:
            out += f"; {self.mishap} found them and took most of it"
        if self.hurt > 0:
            out += " and somebody did not come home"
        return out


def hunt(
    colony: "Colony",
    arrows: float,
    ground: HuntingGround | None = None,
    rng: random.Random | None = None,
    day: int = 0,
) -> Hunt:
    """Send the day's party out, and put what came back on the shelves.

    `arrows` is what the colony's own consumption already took off the shelves,
    so nothing is taken here -- this is only what the shooting was worth. A
    colony out of arrows brings home nothing, which is the whole reason a
    village wants a fletcher.

    Without an `rng` nothing is rolled and the party always comes home whole,
    which is the shape the rest of the sim's economy has: a hunt is a rate,
    and only the wild is a die.
    """
    ground = ground or open_country()
    party = hunters(colony)
    bows = bow_coverage(colony)
    empty = Hunt(day, colony.name, party, bows, max(arrows, 0.0), ground.abundance)
    if arrows <= 0.0 or party <= 0.0 or ground.empty:
        return empty

    # Arrows are the effort; what the party is carrying and how many of them
    # there are decide how much of that effort comes back as an animal.
    effort = arrows * shooting(colony) * recovery(colony) * ground.abundance
    taken = {
        species: effort * share / GAME[species].arrows_each
        for species, share in ground.mix.items()
        if share > 0.0
    }
    bag = {
        "food": sum(GAME[s].meat * n for s, n in taken.items()),
        "cloth": sum(GAME[s].hides * n for s, n in taken.items()),
    }

    mishap = ""
    dropped: dict[str, float] = {}
    hurt = 0.0
    if rng is not None:
        arms = armed_strength(colony)
        met = ground.danger * (1.0 - deterrence(False, arms))
        gored = sum(n * GAME[s].peril for s, n in taken.items()) * (1.0 - 0.5 * bows)
        if ground.predator and rng.random() < met:
            # Hunters are off the road and out of reach of anyone they could
            # have hired, so what answers for them is what they carry.
            mishap = ground.predator
            dropped = {good: qty * PREDATOR_TOLL for good, qty in bag.items()}
            bag = {good: qty - dropped[good] for good, qty in bag.items()}
            if rng.random() < MAULING * (1.0 - ARMS_COVER * arms):
                hurt = 1.0
        elif rng.random() < gored:
            mishap = "boar"
            if rng.random() < MAULING * (1.0 - ARMS_COVER * arms):
                hurt = 1.0

    for good, qty in bag.items():
        if qty > 0.0:
            colony.storage.add(good, qty)

    return Hunt(
        day=day,
        colony=colony.name,
        party=party,
        bows=bows,
        arrows=arrows,
        ground=ground.abundance,
        taken=taken,
        bag={good: qty for good, qty in bag.items() if qty > 0.0},
        mishap=mishap,
        dropped={good: qty for good, qty in dropped.items() if qty > 0.0},
        hurt=hurt,
    )
