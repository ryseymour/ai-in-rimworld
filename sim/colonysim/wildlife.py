"""Wolves and bears: the wild that the roads run through.

Animals are not placed on roads; they live in the terrain, in dens, and the
roads happen to pass near them. Everything else follows from that one fact:

* **Where they are** comes from the land. Wolves want forest, bears want the
  rough country above it, and neither dens next door to a village.
* **How dangerous a road is** is just the sum of the dens it passes, tile by
  tile, with distance falling off. Nothing marks a route as safe or unsafe --
  it is a number a caravan can read before it sets out, which is what lets a
  trader route, load and price against it.
* **Busy roads are safer.** A tile's hazard is divided down by its road tier,
  and heavy traffic pushes nearby dens back. A trunk road wears into a safe
  road; a quiet spur stays wild. That closes a loop with the road wear that
  was already there.

Animals destroy goods. Nothing else in the sim does, so every raid is counted
in `Simulation.lost` and conservation is checked against it -- see
`simulation.goods_in_world`.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .goods import GOOD_NAMES
from .roads import RoadNetwork, Route
from .world import World

Point = tuple[int, int]


@dataclass(frozen=True)
class Species:
    """One kind of animal, and everything that distinguishes it.

    `boldness` is the chance per tile of an encounter right at the den, before
    roads and pack strength are taken into account; `reach` is how far from the
    den that carries at all. Wolves reach further and are met more often; bears
    are met less but are much worse when they are.
    """

    name: str
    #: Relative chance of denning on each kind of ground.
    habitat: dict[str, float]
    reach: float
    boldness: float
    #: Share of a caravan's load taken in a raid.
    appetite: float
    #: Chance a raid turns into the caravan running for home.
    ferocity: float
    #: Chance an unescorted caravan simply drives the animals off.
    timidity: float
    glyph: str


WOLVES = Species(
    name="wolves",
    habitat={"forest": 1.0, "plains": 0.5, "rough": 0.3, "water": 0.0},
    reach=9.0,
    boldness=0.055,
    appetite=0.18,
    ferocity=0.10,
    timidity=0.45,
    glyph="w",
)
BEARS = Species(
    name="bears",
    habitat={"rough": 1.0, "forest": 0.55, "plains": 0.1, "water": 0.0},
    reach=6.0,
    boldness=0.045,
    appetite=0.30,
    ferocity=0.45,
    timidity=0.30,
    glyph="B",
)
SPECIES = {s.name: s for s in (WOLVES, BEARS)}

#: Dens per tile of map. About fourteen on the default 90x45 world.
DEN_DENSITY = 0.0035
#: No den within this many tiles of a village. Villages keep their own ground
#: clear, which is why the danger is on the road and not in the market.
SAFE_RADIUS = 6.0

#: Hazard multiplier by road tier: none, foot path, dirt road, paved. A trunk
#: road is most of the way to safe; a foot path through the trees is not.
TIER_SAFETY = (1.0, 0.9, 0.55, 0.28)

#: What animals take when they raid, per good. They come for the food; cloth
#: is hides and fleece and goes the same way. The rest is trampled, not eaten.
PREY = {"food": 1.0, "cloth": 0.45, "wood": 0.05, "stone": 0.02, "tools": 0.08}

#: A den grows back towards full strength at this rate per day.
REGROWTH = 0.012
#: How hard passing traffic pushes a den back, per day, per tier above a path.
DISTURBANCE = 0.010
#: Strength a den loses when a caravan drives it off.
REPULSE = 0.08

#: An escort makes animals far likelier to give the caravan a wide berth, and
#: cuts what they get away with when they do not.
ESCORT_DETERRENCE = 0.6
ESCORT_SALVAGE = 0.55
#: Coin a guard detail costs per day on the road.
ESCORT_WAGE = 1.5
#: What the caravan's own weapons are worth against animals, and what a colony
#: that armed its people takes off a guard's wage. Bows and spears are most of
#: what a guard detail is for, so a colony that crafts them is paying for
#: bodies rather than for equipment -- see `crafting.armed_strength`.
ARMS_DETERRENCE = 0.5
ARMS_DISCOUNT = 0.45

#: Cap on any single tile's contribution, so a den cannot make a tile certain.
MAX_TILE_HAZARD = 0.35


def deterrence(escorted: bool, arms: float = 0.0) -> float:
    """How likely the animals are to be waved off, 0 to 1.

    Two things do it and they compound rather than add: hired guards, and
    whether the caravan's own people are carrying anything. `arms=0` is the
    world before there were weapons to carry, which is why every default here
    leaves the old numbers exactly as they were.
    """
    base = ESCORT_DETERRENCE if escorted else 0.0
    return base + (1.0 - base) * ARMS_DETERRENCE * max(0.0, min(1.0, arms))


@dataclass
class Den:
    """A wolf pack or a bear's territory. `strength` is 0..1 and moves."""

    id: int
    species: str
    x: int
    y: int
    strength: float = 1.0

    @property
    def kind(self) -> Species:
        return SPECIES[self.species]

    @property
    def pos(self) -> Point:
        return (self.x, self.y)


@dataclass(frozen=True)
class Encounter:
    """What happened when a caravan met something on the road."""

    day: int
    species: str
    den: int
    #: "drove off", "raided", or "routed" -- turned back for home.
    outcome: str
    losses: dict[str, float] = field(default_factory=dict)
    escorted: bool = False

    @property
    def lost_total(self) -> float:
        return sum(self.losses.values())

    def describe(self) -> str:
        if self.outcome == "drove off":
            guard = " (escorted)" if self.escorted else ""
            return f"drove off {self.species}{guard}"
        taken = ", ".join(
            f"{q:.0f} {g}" for g, q in sorted(self.losses.items()) if q >= 0.5
        )
        lost = f" and lost {taken}" if taken else ""
        if self.outcome == "routed":
            return f"turned back by {self.species}{lost}"
        return f"raided by {self.species}{lost}"


@dataclass
class Wilds:
    """Every den on the map, and the danger they add up to."""

    dens: tuple[Den, ...] = ()

    # ------------------------------------------------------------- the field
    def danger_at(self, x: int, y: int) -> float:
        """Chance per tile crossed of meeting something here, ignoring roads."""
        total = 0.0
        for den in self.dens:
            if den.strength <= 0.0:
                continue
            distance = math.hypot(x - den.x, y - den.y)
            kind = den.kind
            if distance >= kind.reach:
                continue
            falloff = (1.0 - distance / kind.reach) ** 2
            total += kind.boldness * den.strength * falloff
        return min(MAX_TILE_HAZARD, total)

    def tile_hazard(self, network: RoadNetwork, x: int, y: int) -> float:
        """The same, as a caravan on the road actually experiences it."""
        danger = self.danger_at(x, y)
        if danger <= 0.0:
            return 0.0
        tile = network.tiles.get((x, y))
        return danger * (TIER_SAFETY[tile.tier] if tile else 1.0)

    def path_hazard(self, network: RoadNetwork, path: tuple[Point, ...]) -> float:
        """Chance of at least one encounter along a carved path."""
        safe = 1.0
        for x, y in path:
            hazard = self.tile_hazard(network, x, y)
            if hazard > 0.0:
                safe *= 1.0 - hazard
        return 1.0 - safe

    def route_hazard(self, network: RoadNetwork, route: Route) -> float:
        return self.path_hazard(network, route.path)

    def journey_hazard(
        self, network: RoadNetwork, legs: tuple[Route, ...]
    ) -> float:
        """Chance of at least one encounter over a whole chain of roads."""
        safe = 1.0
        for leg in legs:
            safe *= 1.0 - self.route_hazard(network, leg)
        return 1.0 - safe

    def worst_den(
        self, network: RoadNetwork, path: tuple[Point, ...]
    ) -> Den | None:
        """The den that contributes most to a path. Used for reporting."""
        best: tuple[float, Den] | None = None
        for den in self.dens:
            weight = self._den_weight(den, network, path)
            if weight <= 0.0:
                continue
            if best is None or weight > best[0]:
                best = (weight, den)
        return None if best is None else best[1]

    def _den_weight(
        self, den: Den, network: RoadNetwork, path: tuple[Point, ...]
    ) -> float:
        if den.strength <= 0.0:
            return 0.0
        kind = den.kind
        total = 0.0
        for x, y in path:
            distance = math.hypot(x - den.x, y - den.y)
            if distance >= kind.reach:
                continue
            tile = network.tiles.get((x, y))
            safety = TIER_SAFETY[tile.tier] if tile else 1.0
            total += (1.0 - distance / kind.reach) ** 2 * kind.boldness * safety
        return total * den.strength

    # ------------------------------------------------------------- behaviour
    def pick_den(
        self, rng: random.Random, network: RoadNetwork, path: tuple[Point, ...]
    ) -> Den | None:
        """Which den a caravan ran into, weighted by how much of the road each
        one overlooks."""
        weights = [(self._den_weight(den, network, path), den) for den in self.dens]
        weights = [(w, d) for w, d in weights if w > 0.0]
        if not weights:
            return None
        roll = rng.random() * sum(w for w, _ in weights)
        for weight, den in weights:
            roll -= weight
            if roll <= 0.0:
                return den
        return weights[-1][1]

    def settle_day(self, network: RoadNetwork) -> None:
        """A day passes in the wild.

        Packs recover towards full strength, and traffic on the roads within
        reach pushes them back. Where the two balance decides whether a road
        stays dangerous once it is busy.
        """
        for den in self.dens:
            pressure = 0.0
            kind = den.kind
            span = int(kind.reach)
            for dy in range(-span, span + 1):
                for dx in range(-span, span + 1):
                    tile = network.tiles.get((den.x + dx, den.y + dy))
                    if tile is None or dx * dx + dy * dy > kind.reach**2:
                        continue
                    pressure += DISTURBANCE * (tile.tier - 1)
            den.strength = max(0.0, min(1.0, den.strength + REGROWTH - pressure))


def populate(world: World, seed: int, density: float = DEN_DENSITY) -> Wilds:
    """Scatter dens over a world's terrain.

    Rejection sampling against each species' habitat, so where the animals end
    up is a property of the map rather than of the road network: a world of
    forest and crags is a dangerous world to trade across, and the same seed
    always gives the same one.
    """
    terrain = world.terrain
    rng = random.Random(seed ^ 0xB4A2)
    target = max(0, round(terrain.width * terrain.height * density))
    occupied = {s.pos for s in world.settlements}

    dens: list[Den] = []
    attempts = 0
    while len(dens) < target and attempts < target * 200:
        attempts += 1
        x = rng.randrange(terrain.width)
        y = rng.randrange(terrain.height)
        kind_name = terrain.kind(x, y)
        if (x, y) in occupied:
            continue
        if any(
            math.hypot(x - s.x, y - s.y) < SAFE_RADIUS for s in world.settlements
        ):
            continue
        suitability = {s.name: s.habitat.get(kind_name, 0.0) for s in SPECIES.values()}
        total = sum(suitability.values())
        if total <= 0.0 or rng.random() > max(suitability.values()):
            continue
        roll = rng.random() * total
        species = WOLVES.name
        for name, weight in sorted(suitability.items()):
            roll -= weight
            if roll <= 0.0:
                species = name
                break
        dens.append(Den(len(dens), species, x, y))
        occupied.add((x, y))

    return Wilds(tuple(dens))


# --------------------------------------------------------------------------
# What a trader does about it
# --------------------------------------------------------------------------

#: Expected share of a load lost when a caravan is caught, averaged over the
#: species and outcomes. What a trader uses to price the risk before it goes.
TYPICAL_LOSS = 0.25


def expected_loss(
    hazard: float, cargo_value: float, escorted: bool = False, arms: float = 0.0
) -> float:
    """What a trader should expect a dangerous road to cost it.

    Deliberately an estimate and not the truth: it averages the species, so a
    trader that reasons with it can still be badly wrong about the particular
    bear it meets. That is the same shape as the stale `MarketView` the trade
    code already plans against.
    """
    loss = TYPICAL_LOSS * (ESCORT_SALVAGE if escorted else 1.0)
    deterred = hazard * (1.0 - deterrence(escorted, arms))
    return deterred * cargo_value * loss


def escort_cost(days: float, arms: float = 0.0) -> float:
    """What a guard detail asks for the trip.

    Less from a colony that arms its own people: the guards are being paid to
    walk, not to be equipped. This is the cheaper half of what weapons buy a
    colony on the road; `deterrence` is the better half.
    """
    return ESCORT_WAGE * days * (1.0 - ARMS_DISCOUNT * max(0.0, min(1.0, arms)))


def per_day_hazard(journey_hazard: float, days: float) -> float:
    """Spread a whole journey's risk over the days it takes to walk it."""
    if days <= 0 or journey_hazard <= 0:
        return 0.0
    return 1.0 - (1.0 - min(journey_hazard, 0.999)) ** (1.0 / days)


def raid(
    rng: random.Random,
    den: Den,
    cargo: dict[str, float],
    escorted: bool,
    day: int,
    arms: float = 0.0,
) -> Encounter:
    """Resolve one meeting on the road, taking goods out of `cargo` in place.

    Three ways it can go: the caravan drives them off, the animals get at the
    load, or -- a bear, usually -- the caravan drops what it must and runs for
    home. An escort makes the first much likelier and the last two cheaper.
    """
    kind = den.kind
    guard = deterrence(escorted, arms)
    drive_off = kind.timidity + (1.0 - kind.timidity) * guard
    if rng.random() < drive_off:
        den.strength = max(0.0, den.strength - REPULSE)
        return Encounter(day, kind.name, den.id, "drove off", {}, escorted)

    share = kind.appetite * den.strength * (ESCORT_SALVAGE if escorted else 1.0)
    losses: dict[str, float] = {}
    for good in GOOD_NAMES:
        held = cargo.get(good, 0.0)
        if held <= 0.0:
            continue
        taken = min(held, held * share * PREY.get(good, 0.0))
        if taken <= 1e-9:
            continue
        cargo[good] = held - taken
        if cargo[good] <= 1e-9:
            del cargo[good]
        losses[good] = taken

    outcome = "raided"
    if rng.random() < kind.ferocity * (1.0 - guard):
        outcome = "routed"
    return Encounter(day, kind.name, den.id, outcome, losses, escorted)
