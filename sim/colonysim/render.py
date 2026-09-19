"""ASCII render of a world and its roads."""
from __future__ import annotations

from .roads import RoadNetwork
from .wildlife import Wilds
from .world import World

TERRAIN_GLYPH = {"water": "~", "plains": ".", "forest": '"', "rough": "^"}
#: Road glyph by tier: foot path, dirt road, paved.
ROAD_GLYPH = {1: ":", 2: "-", 3: "="}


def render(
    world: World, network: RoadNetwork | None = None, wilds: Wilds | None = None
) -> str:
    terrain = world.terrain
    grid = [
        [TERRAIN_GLYPH[terrain.kind(x, y)] for x in range(terrain.width)]
        for y in range(terrain.height)
    ]

    if network is not None:
        for (x, y), road in network.tiles.items():
            grid[y][x] = ROAD_GLYPH.get(road.tier, ":")

    # Dens go on after the roads: where a road runs past a den, the den is
    # what the caravan cares about.
    if wilds is not None:
        for den in wilds.dens:
            if den.strength > 0.0:
                grid[den.y][den.x] = den.kind.glyph

    for s in world.settlements:
        grid[s.y][s.x] = str(s.id) if s.id < 10 else "#"

    return "\n".join("".join(row) for row in grid)


def legend(
    world: World, network: RoadNetwork | None = None, wilds: Wilds | None = None
) -> str:
    lines = [f"{s.id} {s.name} ({s.x},{s.y})" for s in world.settlements]
    if wilds is not None and wilds.dens:
        counts: dict[str, int] = {}
        for den in wilds.dens:
            counts[den.species] = counts.get(den.species, 0) + 1
        lines.append("")
        tally = ", ".join(f"{n} {species}" for species, n in sorted(counts.items()))
        lines.append(f"dens: {tally}")
    if network is not None:
        lines.append("")
        for (a, b), route in sorted(network.routes.items()):
            lines.append(
                f"{world.settlements[a].name} - {world.settlements[b].name}: "
                f"{len(route.path)} tiles, cost {route.cost:.0f}"
            )
    return "\n".join(lines)
