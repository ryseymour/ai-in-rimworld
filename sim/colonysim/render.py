"""ASCII render of a world and its roads."""
from __future__ import annotations

from .hunting import Herds
from .roads import RoadNetwork
from .wildlife import Wilds
from .world import World

TERRAIN_GLYPH = {"water": "~", "plains": ".", "forest": '"', "rough": "^"}
#: Road glyph by tier: foot path, dirt road, paved.
ROAD_GLYPH = {1: ":", 2: "-", 3: "="}


#: A caravan on the road.
CARAVAN_GLYPH = "@"


def render(
    world: World,
    network: RoadNetwork | None = None,
    caravans: "list | None" = None,
    wilds: Wilds | None = None,
    herds: Herds | None = None,
) -> str:
    terrain = world.terrain
    grid = [
        [TERRAIN_GLYPH[terrain.kind(x, y)] for x in range(terrain.width)]
        for y in range(terrain.height)
    ]

    if network is not None:
        for (x, y), road in network.tiles.items():
            grid[y][x] = ROAD_GLYPH.get(road.tier, ":")

    # Game first, then the dens on top: where a herd grazes under a wolf pack,
    # the wolves are the thing anyone walking out there cares about.
    if herds is not None:
        for herd in herds.herds:
            if herd.strength > 0.0:
                grid[herd.y][herd.x] = herd.kind.glyph

    # Dens go on after the roads: where a road runs past a den, the den is
    # what the caravan cares about.
    if wilds is not None:
        for den in wilds.dens:
            if den.strength > 0.0:
                grid[den.y][den.x] = den.kind.glyph

    for s in world.settlements:
        grid[s.y][s.x] = str(s.id) if s.id < 10 else "#"

    # Caravans last, so a trader is never hidden under the road it is on.
    for caravan in caravans or ():
        spot = caravan.position
        if spot is not None and terrain.in_bounds(*spot):
            grid[spot[1]][spot[0]] = CARAVAN_GLYPH

    return "\n".join("".join(row) for row in grid)


def legend(
    world: World,
    network: RoadNetwork | None = None,
    wilds: Wilds | None = None,
    herds: Herds | None = None,
) -> str:
    lines = [f"{s.id} {s.name} ({s.x},{s.y})" for s in world.settlements]
    if (wilds is not None and wilds.dens) or (herds is not None and herds.herds):
        lines.append("")
    if wilds is not None and wilds.dens:
        counts: dict[str, int] = {}
        for den in wilds.dens:
            counts[den.species] = counts.get(den.species, 0) + 1
        tally = ", ".join(f"{n} {species}" for species, n in sorted(counts.items()))
        lines.append(f"dens: {tally}")
    if herds is not None and herds.herds:
        tally = ", ".join(f"{n} {species}" for species, n in herds.tally().items())
        lines.append(f"game: {tally}")
    if network is not None:
        lines.append("")
        for (a, b), route in sorted(network.routes.items()):
            lines.append(
                f"{world.settlements[a].name} - {world.settlements[b].name}: "
                f"{len(route.path)} tiles, cost {route.cost:.0f}"
            )
    return "\n".join(lines)
