"""Settlements on a terrain grid."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .terrain import Terrain, generate_terrain

NAMES = (
    "Ashford", "Brackwater", "Coldhollow", "Dunmarch", "Eastmoor", "Fenwick",
    "Greyfell", "Hearthwood", "Ironmere", "Kestrel", "Longbarrow", "Millbrook",
    "Northgate", "Oakhaven", "Pinecross", "Quarryhill", "Redstone", "Stonewick",
    "Thornvale", "Westmarch",
)


@dataclass(frozen=True)
class Settlement:
    """A village. `id` is stable across a world's lifetime."""

    id: int
    name: str
    x: int
    y: int

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass(frozen=True)
class World:
    terrain: Terrain
    settlements: tuple[Settlement, ...]

    def by_id(self, sid: int) -> Settlement:
        return self.settlements[sid]


def place_settlements(
    terrain: Terrain, count: int, seed: int, min_separation: float = 12.0
) -> tuple[Settlement, ...]:
    """Scatter villages on habitable ground, no two closer than `min_separation`.

    Rejection sampling with a shrinking separation, so a crowded map still
    places every settlement asked for rather than silently returning fewer.
    """
    rng = random.Random(seed ^ 0x5EED)
    placed: list[Settlement] = []
    separation = min_separation

    attempts = 0
    while len(placed) < count:
        attempts += 1
        if attempts > 400:  # map is too full at this spacing; relax and retry
            separation *= 0.8
            attempts = 0
            if separation < 2.0:
                break

        x = rng.randrange(2, terrain.width - 2)
        y = rng.randrange(2, terrain.height - 2)
        if terrain.is_water(x, y) or terrain.kind(x, y) == "rough":
            continue
        if any((x - s.x) ** 2 + (y - s.y) ** 2 < separation**2 for s in placed):
            continue

        placed.append(Settlement(len(placed), NAMES[len(placed) % len(NAMES)], x, y))

    return tuple(placed)


def generate_world(
    width: int = 90,
    height: int = 45,
    settlements: int = 6,
    seed: int = 1,
) -> World:
    terrain = generate_terrain(width, height, seed)
    return World(terrain, place_settlements(terrain, settlements, seed))
