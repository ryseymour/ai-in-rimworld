"""Terrain grid: elevation, water, and the movement cost that shapes roads.

The road generator never looks at tiles directly; it only asks this module what
a tile costs to cross. Changing the cost model here changes where roads go.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

WATER_LEVEL = 0.34
FOREST_LEVEL = 0.55
ROUGH_LEVEL = 0.72

#: Cost of crossing one tile, before slope is added. Water is not impassable --
#: a road may ford a narrow channel if going around is dearer -- but it is
#: expensive enough that it only happens at the narrow places.
BASE_COST = {
    "water": 14.0,
    "plains": 1.0,
    "forest": 1.9,
    "rough": 3.2,
}

#: How hard a road works to avoid climbing. This is the term that makes
#: generated roads follow valleys and contours instead of running straight, so
#: it matters more to how the network looks than anything else here.
SLOPE_WEIGHT = 34.0

CHEAPEST_TILE = min(BASE_COST.values())


@dataclass(frozen=True)
class Terrain:
    """A heightmap. Elevation is 0..1, row-major."""

    width: int
    height: int
    elevation: tuple[float, ...]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def elev(self, x: int, y: int) -> float:
        return self.elevation[y * self.width + x]

    def kind(self, x: int, y: int) -> str:
        e = self.elev(x, y)
        if e < WATER_LEVEL:
            return "water"
        if e < FOREST_LEVEL:
            return "plains"
        if e < ROUGH_LEVEL:
            return "forest"
        return "rough"

    def base_cost(self, x: int, y: int) -> float:
        return BASE_COST[self.kind(x, y)]

    def is_water(self, x: int, y: int) -> bool:
        return self.elev(x, y) < WATER_LEVEL


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _lattice(rng: random.Random, w: int, h: int) -> list[float]:
    return [rng.random() for _ in range(w * h)]


def _sample(grid: list[float], gw: int, gh: int, fx: float, fy: float) -> float:
    """Bilinear sample of a lattice with smoothstepped interpolation."""
    x = fx * (gw - 1)
    y = fy * (gh - 1)
    x0, y0 = int(x), int(y)
    x1, y1 = min(x0 + 1, gw - 1), min(y0 + 1, gh - 1)
    tx, ty = _smoothstep(x - x0), _smoothstep(y - y0)

    top = grid[y0 * gw + x0] * (1 - tx) + grid[y0 * gw + x1] * tx
    bot = grid[y1 * gw + x0] * (1 - tx) + grid[y1 * gw + x1] * tx
    return top * (1 - ty) + bot * ty


def generate_terrain(width: int, height: int, seed: int, octaves: int = 4) -> Terrain:
    """Value noise summed over octaves, normalised to 0..1.

    Seeded end to end: the same seed and size always give the same map, which
    is what lets a save regenerate its world and lets tests assert on it.
    """
    layers: list[tuple[list[float], int, int, float]] = []
    amplitude = 1.0
    total_amplitude = 0.0
    for octave in range(octaves):
        rng = random.Random((seed << 8) ^ octave)
        gw = gh = 2 ** (octave + 1) + 1
        layers.append((_lattice(rng, gw, gh), gw, gh, amplitude))
        total_amplitude += amplitude
        amplitude *= 0.5

    values: list[float] = []
    for y in range(height):
        fy = y / max(height - 1, 1)
        for x in range(width):
            fx = x / max(width - 1, 1)
            v = sum(_sample(g, gw, gh, fx, fy) * amp for g, gw, gh, amp in layers)
            values.append(v / total_amplitude)

    lo, hi = min(values), max(values)
    span = hi - lo or 1.0
    return Terrain(width, height, tuple((v - lo) / span for v in values))
