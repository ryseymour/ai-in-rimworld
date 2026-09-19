"""Procedural road generation between settlements.

Three ideas do the work here:

* **Which villages connect.** A minimum spanning tree over terrain-aware costs
  guarantees every village is reachable; a fraction of the rejected candidate
  edges is added back so the network has loops and alternate routes instead of
  being a bare tree.
* **Where a road runs.** A* across the terrain, with slope penalised much more
  heavily than distance.
* **Why roads bundle.** A tile that already carries road is cheap to reuse, so
  later routes bend to join earlier ones and trunk roads form. Routes are
  therefore carved busiest-first: the trunks get laid down before the traffic
  that should merge onto them.
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass, field

from .terrain import CHEAPEST_TILE, SLOPE_WEIGHT, Terrain
from .world import World

#: Multiplier on a tile that already carries a road. The single knob that
#: decides whether the network looks like a road system or like a pile of
#: independent tracks.
ROAD_REUSE = 0.28

#: Movement multiplier by tier: none, foot path, dirt road, paved.
TIER_SPEED = (1.0, 1.3, 1.6, 2.0)
#: Accumulated traffic at which a tile is promoted into each tier. Set so a
#: busy trunk route reaches paved over a season while a quiet spur stays dirt.
TIER_THRESHOLD = (0.0, 12.0, 70.0, 260.0)

SQRT2 = math.sqrt(2.0)
_NEIGHBOURS = (
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2),
)

Point = tuple[int, int]


@dataclass
class RoadTile:
    tier: int = 1
    traffic: float = 0.0

    @property
    def speed(self) -> float:
        return TIER_SPEED[self.tier]


@dataclass(frozen=True)
class Route:
    """A carved road between two settlements."""

    a: int
    b: int
    path: tuple[Point, ...]
    cost: float

    @property
    def key(self) -> tuple[int, int]:
        return (min(self.a, self.b), max(self.a, self.b))


@dataclass
class RoadNetwork:
    tiles: dict[Point, RoadTile] = field(default_factory=dict)
    routes: dict[tuple[int, int], Route] = field(default_factory=dict)

    def has_road(self, x: int, y: int) -> bool:
        return (x, y) in self.tiles

    def neighbours(self, sid: int) -> list[int]:
        out = [b for (a, b) in self.routes if a == sid]
        out += [a for (a, b) in self.routes if b == sid]
        return sorted(out)

    def travel_cost(self, a: int, b: int) -> float | None:
        """Cost of the direct route between two settlements, if one exists."""
        route = self.routes.get((min(a, b), max(a, b)))
        return None if route is None else route.cost


# --------------------------------------------------------------------------
# Pathing
# --------------------------------------------------------------------------

def step_cost(
    terrain: Terrain, network: RoadNetwork, frm: Point, to: Point, diagonal: float
) -> float:
    """What it costs to walk from one adjacent tile to another."""
    x, y = to
    cost = terrain.base_cost(x, y)
    cost += SLOPE_WEIGHT * abs(terrain.elev(x, y) - terrain.elev(*frm))
    if (x, y) in network.tiles:
        cost *= ROAD_REUSE
    return cost * diagonal


def _octile(a: Point, b: Point) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return (dx + dy) + (SQRT2 - 2.0) * min(dx, dy)


def find_path(
    terrain: Terrain, network: RoadNetwork, start: Point, goal: Point
) -> tuple[tuple[Point, ...], float]:
    """A* from start to goal. Returns the path (inclusive) and its cost.

    The heuristic assumes every remaining tile could be the cheapest possible
    one -- plains already carrying road -- which keeps it admissible however
    much road has been laid down already.
    """
    floor = CHEAPEST_TILE * ROAD_REUSE
    open_heap: list[tuple[float, int, Point]] = [(0.0, 0, start)]
    came: dict[Point, Point] = {}
    best: dict[Point, float] = {start: 0.0}
    counter = 0

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            break
        current_cost = best[current]

        for dx, dy, diagonal in _NEIGHBOURS:
            nxt = (current[0] + dx, current[1] + dy)
            if not terrain.in_bounds(*nxt):
                continue
            cost = current_cost + step_cost(terrain, network, current, nxt, diagonal)
            if cost < best.get(nxt, math.inf):
                best[nxt] = cost
                came[nxt] = current
                counter += 1
                heapq.heappush(open_heap, (cost + _octile(nxt, goal) * floor, counter, nxt))

    if goal not in best:
        return (), math.inf

    path = [goal]
    while path[-1] != start:
        path.append(came[path[-1]])
    path.reverse()
    return tuple(path), best[goal]


# --------------------------------------------------------------------------
# Which settlements connect
# --------------------------------------------------------------------------

def gabriel_edges(world: World) -> list[tuple[int, int]]:
    """Gabriel graph: keep an edge when no third village sits in the circle
    having that edge as its diameter. Gives plausible local connections and
    drops the long edges that would cross the map."""
    pts = world.settlements
    edges = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            mx = (pts[i].x + pts[j].x) / 2.0
            my = (pts[i].y + pts[j].y) / 2.0
            r2 = ((pts[i].x - pts[j].x) ** 2 + (pts[i].y - pts[j].y) ** 2) / 4.0
            if all(
                (pts[k].x - mx) ** 2 + (pts[k].y - my) ** 2 >= r2
                for k in range(len(pts))
                if k not in (i, j)
            ):
                edges.append((i, j))
    return edges


def nearest_edges(world: World, k: int = 3) -> list[tuple[int, int]]:
    pts = world.settlements
    edges = set()
    for i, a in enumerate(pts):
        by_distance = sorted(
            (j for j in range(len(pts)) if j != i),
            key=lambda j: ((pts[j].x - a.x) ** 2 + (pts[j].y - a.y) ** 2, j),
        )
        for j in by_distance[:k]:
            edges.add((min(i, j), max(i, j)))
    return sorted(edges)


def _spanning_tree(
    count: int, edges: list[tuple[int, int]], cost: dict[tuple[int, int], float]
) -> list[tuple[int, int]]:
    """Kruskal. Ties break on the edge itself so the result is deterministic."""
    parent = list(range(count))

    def find(n: int) -> int:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    tree = []
    for edge in sorted(edges, key=lambda e: (cost[e], e)):
        ra, rb = find(edge[0]), find(edge[1])
        if ra != rb:
            parent[ra] = rb
            tree.append(edge)
    return tree


def _tree_traffic(count: int, tree: list[tuple[int, int]]) -> dict[tuple[int, int], float]:
    """Expected traffic on each tree edge.

    Removing an edge splits the tree into two sides; every pair of villages
    that straddles the split must use it. So traffic is the product of the two
    side sizes -- exact edge betweenness on a tree, and the ordering that makes
    trunk roads form first.
    """
    adjacency: dict[int, list[int]] = {n: [] for n in range(count)}
    for a, b in tree:
        adjacency[a].append(b)
        adjacency[b].append(a)

    traffic = {}
    for edge in tree:
        seen = {edge[0]}
        stack = [edge[0]]
        while stack:  # flood one side without crossing the edge under test
            node = stack.pop()
            for nxt in adjacency[node]:
                if nxt not in seen and (min(node, nxt), max(node, nxt)) != edge:
                    seen.add(nxt)
                    stack.append(nxt)
        traffic[edge] = float(len(seen) * (count - len(seen)))
    return traffic


def _tree_distance(
    count: int, tree: list[tuple[int, int]], cost: dict[tuple[int, int], float]
) -> dict[tuple[int, int], float]:
    """Shortest path through the tree alone, for every pair of villages."""
    adjacency: dict[int, list[int]] = {n: [] for n in range(count)}
    for a, b in tree:
        adjacency[a].append(b)
        adjacency[b].append(a)

    out: dict[tuple[int, int], float] = {}
    for src in range(count):
        dist = {src: 0.0}
        stack = [src]
        while stack:
            node = stack.pop()
            for nxt in adjacency[node]:
                if nxt not in dist:
                    edge = (min(node, nxt), max(node, nxt))
                    dist[nxt] = dist[node] + cost[edge]
                    stack.append(nxt)
        for dst, d in dist.items():
            out[(min(src, dst), max(src, dst))] = d
    return out


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def generate_roads(world: World, extra_edge_fraction: float = 0.25) -> RoadNetwork:
    """Build the road network for a world.

    Deterministic: same world in, same roads out.
    """
    network = RoadNetwork()
    count = len(world.settlements)
    if count < 2:
        return network

    candidates = sorted(set(gabriel_edges(world)) | set(nearest_edges(world)))

    # Cost every candidate on bare terrain, before any road exists, so the
    # choice of which villages connect does not depend on carving order.
    bare = RoadNetwork()
    cost: dict[tuple[int, int], float] = {}
    for a, b in candidates:
        _, c = find_path(
            world.terrain, bare, world.settlements[a].pos, world.settlements[b].pos
        )
        cost[(a, b)] = c

    tree = _spanning_tree(count, candidates, cost)
    traffic = _tree_traffic(count, tree)
    tree_distance = _tree_distance(count, tree, cost)

    # Add back the shortcuts that save the most: edges whose detour through the
    # tree is worst relative to going direct.
    rest = [e for e in candidates if e not in traffic]
    rest.sort(key=lambda e: (-(tree_distance.get(e, math.inf) / cost[e]), e))
    keep = round(len(rest) * extra_edge_fraction)
    extras = rest[:keep]

    order = sorted(tree, key=lambda e: (-traffic[e], e)) + extras

    for a, b in order:
        path, c = find_path(
            world.terrain, network, world.settlements[a].pos, world.settlements[b].pos
        )
        if not path:
            continue
        network.routes[(a, b)] = Route(a, b, path, c)
        for tile in path:
            network.tiles.setdefault(tile, RoadTile())

    return network


# --------------------------------------------------------------------------
# Wear
# --------------------------------------------------------------------------

def apply_traffic(network: RoadNetwork, route: Route, amount: float = 1.0) -> None:
    """Record a caravan having travelled a route, promoting tiers as it goes."""
    for tile in route.path:
        road = network.tiles.setdefault(tile, RoadTile())
        road.traffic += amount
        while road.tier + 1 < len(TIER_THRESHOLD) and road.traffic >= TIER_THRESHOLD[road.tier + 1]:
            road.tier += 1


def decay(network: RoadNetwork, rate: float = 0.5) -> None:
    """Unused roads grass over. Tiles that fall below foot path are removed."""
    for tile, road in list(network.tiles.items()):
        road.traffic = max(0.0, road.traffic - rate)
        while road.tier > 1 and road.traffic < TIER_THRESHOLD[road.tier]:
            road.tier -= 1


def travel_cost(
    terrain: Terrain,
    network: RoadNetwork,
    path: tuple[Point, ...],
    slowdown: Callable[[float], float] | None = None,
) -> float:
    """What it costs to walk a carved path today.

    Unlike the cost used while carving -- which discounts road tiles to make
    routes bundle -- this is real travel: terrain cost divided by the speed of
    whatever road is on the tile. So a route that wears up to paved becomes
    genuinely faster to drive a caravan down.

    `slowdown` is how something the road does not know about -- weather --
    makes the same tile dearer to cross, given that tile's own tier. Handing it
    a weather's own slowdown is the whole of how a storm reaches the road
    graph, and it is asked per tile rather than per route, so a paved stretch
    shelters the caravan on it and the foot path beside it does not.
    """
    total = 0.0
    for frm, to in zip(path, path[1:]):
        diagonal = SQRT2 if frm[0] != to[0] and frm[1] != to[1] else 1.0
        cost = terrain.base_cost(*to)
        cost += SLOPE_WEIGHT * abs(terrain.elev(*to) - terrain.elev(*frm))
        tile = network.tiles.get(to)
        step = cost * diagonal / (tile.speed if tile else 1.0)
        if slowdown is not None:
            step *= slowdown(tile.tier if tile else 0)
        total += step
    return total


def path_grade(network: RoadNetwork, path: tuple[Point, ...]) -> float:
    """Mean road tier along a run of tiles: how good the way there actually is.

    The one number weather is answered with. A mean rather than the worst tile,
    because a route is walked whole: one bad furlong on an otherwise paved
    trunk road is a slow hour, not a closed road.
    """
    if not path:
        return 0.0
    return sum(
        network.tiles[tile].tier if tile in network.tiles else 0 for tile in path
    ) / len(path)


def route_grade(network: RoadNetwork, route: Route) -> float:
    return path_grade(network, route.path)


def journey_grade(network: RoadNetwork, legs: tuple[Route, ...]) -> float:
    """The same over a chain of roads, each leg weighted by how long it is."""
    tiles = tuple(tile for leg in legs for tile in leg.path)
    return path_grade(network, tiles)


def route_between(
    network: RoadNetwork,
    a: int,
    b: int,
    surcharge: Callable[[Route], float] | None = None,
    blocked: Callable[[Route], bool] | None = None,
) -> tuple[Route, ...]:
    """The cheapest chain of roads from one settlement to another.

    Direct neighbours give a single leg; anywhere else is reached by passing
    through the villages in between. Dijkstra over the route graph, so a
    well-connected village becomes a natural staging post for trade.

    `surcharge` adds to a leg's cost without changing it: it is how something
    a road does not know about -- wolves, weather -- makes a route less
    attractive than its length alone suggests, so the search will take a
    longer way round to avoid it. Costs are returned as carved, not surcharged,
    so travel time is unaffected by whatever the detour was chosen for.

    `blocked` takes a leg out of the graph altogether, which is what a road
    closed by weather is: not a dear way through but no way through. The search
    then finds whatever open chain is left, so a snowed-in pass pushes trade
    onto the long valley road rather than stopping it.
    """
    if a == b:
        return ()

    adjacency: dict[int, list[tuple[int, Route]]] = {}
    for (x, y), route in network.routes.items():
        adjacency.setdefault(x, []).append((y, route))
        adjacency.setdefault(y, []).append((x, route))

    queue: list[tuple[float, int, int]] = [(0.0, a, -1)]
    best: dict[int, float] = {a: 0.0}
    came: dict[int, tuple[int, Route]] = {}
    counter = 0

    while queue:
        cost, node, _ = heapq.heappop(queue)
        if node == b:
            break
        if cost > best.get(node, math.inf):
            continue
        for nxt, route in sorted(adjacency.get(node, []), key=lambda pair: pair[0]):
            if blocked is not None and blocked(route):
                continue
            through = cost + route.cost
            if surcharge is not None:
                through += surcharge(route)
            if through < best.get(nxt, math.inf):
                best[nxt] = through
                came[nxt] = (node, route)
                counter += 1
                heapq.heappush(queue, (through, nxt, counter))

    if b not in came:
        return ()

    legs = []
    node = b
    while node != a:
        node, route = came[node]
        legs.append(route)
    legs.reverse()
    return tuple(legs)


def road_overlay(network: RoadNetwork) -> list[dict]:
    """Every road tile as plain data, for a renderer to draw.

    JSON-safe and ordered, so another UI -- a build-mode overlay, an existing
    game's tile renderer -- can draw the roads without knowing anything about
    this package's objects. Tile-level detail: use it where the map is drawn
    at tile resolution.
    """
    return [
        {"x": x, "y": y, "tier": tile.tier, "speed": tile.speed}
        for (x, y), tile in sorted(network.tiles.items())
    ]


def road_links(network: RoadNetwork, world: World) -> list[dict]:
    """Each route as a single line between two settlements.

    For anywhere the map is drawn too small for individual tiles to read -- a
    minimap, an overview panel -- where 120 separate road tiles are noise but
    the shape of the network is the point. `tier` is the best grade the route
    reaches, which is what to weight the line by.
    """
    links = []
    for (a, b), route in sorted(network.routes.items()):
        tiers = [network.tiles[t].tier for t in route.path if t in network.tiles]
        links.append(
            {
                "from": a,
                "to": b,
                "from_name": world.settlements[a].name,
                "to_name": world.settlements[b].name,
                "x1": world.settlements[a].x,
                "y1": world.settlements[a].y,
                "x2": world.settlements[b].x,
                "y2": world.settlements[b].y,
                "tier": max(tiers) if tiers else 1,
                "tiles": len(route.path),
            }
        )
    return links
