"""ASCII render of a world and its roads."""
from __future__ import annotations

from .roads import RoadNetwork
from .world import World

TERRAIN_GLYPH = {"water": "~", "plains": ".", "forest": '"', "rough": "^"}
#: Road glyph by tier: foot path, dirt road, paved.
ROAD_GLYPH = {1: ":", 2: "-", 3: "="}


def render(world: World, network: RoadNetwork | None = None) -> str:
    terrain = world.terrain
    grid = [
        [TERRAIN_GLYPH[terrain.kind(x, y)] for x in range(terrain.width)]
        for y in range(terrain.height)
    ]

    if network is not None:
        for (x, y), road in network.tiles.items():
            grid[y][x] = ROAD_GLYPH.get(road.tier, ":")

    for s in world.settlements:
        grid[s.y][s.x] = str(s.id) if s.id < 10 else "#"

    return "\n".join("".join(row) for row in grid)


def legend(world: World, network: RoadNetwork | None = None) -> str:
    lines = [f"{s.id} {s.name} ({s.x},{s.y})" for s in world.settlements]
    if network is not None:
        lines.append("")
        for (a, b), route in sorted(network.routes.items()):
            lines.append(
                f"{world.settlements[a].name} - {world.settlements[b].name}: "
                f"{len(route.path)} tiles, cost {route.cost:.0f}"
            )
    return "\n".join(lines)
