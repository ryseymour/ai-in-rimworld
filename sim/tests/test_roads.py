"""The assertions the design names: reachability, determinism, bundling, wear."""
from __future__ import annotations

import math

import pytest

from colonysim.roads import (
    ROAD_REUSE,
    RoadNetwork,
    RoadTile,
    TIER_THRESHOLD,
    apply_traffic,
    decay,
    find_path,
    gabriel_edges,
    generate_roads,
)
from colonysim.terrain import generate_terrain
from colonysim.world import Settlement, World, generate_world

SEEDS = [1, 7, 23, 99]


def road_component(network: RoadNetwork, start):
    """Flood fill the road tiles, 8-connected, from one tile."""
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nxt = (x + dx, y + dy)
                if nxt in network.tiles and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
    return seen


@pytest.mark.parametrize("seed", SEEDS)
def test_every_settlement_is_reachable(seed):
    """The spanning tree is what guarantees this; without it a village can be
    stranded and any trader sent there is stuck forever."""
    world = generate_world(seed=seed)
    network = generate_roads(world)

    reached = road_component(network, world.settlements[0].pos)
    stranded = [s.name for s in world.settlements if s.pos not in reached]
    assert stranded == []


@pytest.mark.parametrize("seed", SEEDS)
def test_generation_is_deterministic(seed):
    """A save has to regenerate the same world, or nothing is reproducible."""
    a = generate_roads(generate_world(seed=seed))
    b = generate_roads(generate_world(seed=seed))

    assert sorted(a.tiles) == sorted(b.tiles)
    assert {k: v.path for k, v in a.routes.items()} == {k: v.path for k, v in b.routes.items()}


def test_different_seeds_give_different_worlds():
    assert sorted(generate_roads(generate_world(seed=1)).tiles) != sorted(
        generate_roads(generate_world(seed=2)).tiles
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_routes_share_tiles_into_trunk_roads(seed):
    """The road-reuse discount should make later routes join earlier ones. If
    every route carved its own track the totals here would be equal."""
    world = generate_world(seed=seed)
    network = generate_roads(world)

    laid = sum(len(r.path) for r in network.routes.values())
    assert len(network.tiles) < laid


@pytest.mark.parametrize("seed", SEEDS)
def test_roads_mostly_avoid_water(seed):
    """Water may be forded where going round is dearer, but a road that runs
    through the lake means the cost model is broken."""
    world = generate_world(seed=seed)
    network = generate_roads(world)

    wet = sum(1 for (x, y) in network.tiles if world.terrain.is_water(x, y))
    assert wet / len(network.tiles) < 0.10


@pytest.mark.parametrize("seed", SEEDS)
def test_network_has_loops_not_just_a_tree(seed):
    """A bare spanning tree has exactly n-1 edges and one route to anywhere."""
    world = generate_world(seed=seed)
    network = generate_roads(world)

    assert len(network.routes) >= len(world.settlements) - 1


def test_paths_are_contiguous_and_end_where_asked():
    world = generate_world(seed=7)
    network = generate_roads(world)

    for (a, b), route in network.routes.items():
        assert route.path[0] == world.settlements[a].pos
        assert route.path[-1] == world.settlements[b].pos
        for (x1, y1), (x2, y2) in zip(route.path, route.path[1:]):
            assert max(abs(x1 - x2), abs(y1 - y2)) == 1


def test_existing_road_is_cheaper_to_follow():
    """The discount has to actually bite, or nothing bundles."""
    terrain = generate_terrain(40, 40, 5)
    bare = RoadNetwork()
    start, goal = (2, 20), (37, 20)

    path, plain_cost = find_path(terrain, bare, start, goal)

    paved = RoadNetwork(tiles={tile: RoadTile() for tile in path})
    _, paved_cost = find_path(terrain, paved, start, goal)

    assert paved_cost == pytest.approx(plain_cost * ROAD_REUSE, rel=0.02)


def test_path_between_disconnected_points_is_infinite():
    """Nothing is walled off on a normal map, but the caller must be able to
    tell, rather than getting a nonsense path."""
    terrain = generate_terrain(10, 10, 1)
    path, cost = find_path(terrain, RoadNetwork(), (0, 0), (40, 40))
    assert path == ()
    assert cost == math.inf


def test_traffic_promotes_tiers_and_disuse_decays_them():
    world = generate_world(seed=7)
    network = generate_roads(world)
    route = next(iter(network.routes.values()))

    assert all(network.tiles[t].tier == 1 for t in route.path)

    apply_traffic(network, route, TIER_THRESHOLD[3])
    assert all(network.tiles[t].tier == 3 for t in route.path)

    decay(network, rate=TIER_THRESHOLD[3])
    assert all(network.tiles[t].tier == 1 for t in route.path)


def test_gabriel_graph_drops_the_edge_across_a_midpoint():
    """Three villages in a line: the long edge should be rejected because the
    middle one sits inside its circle. This is what stops the map turning into
    a spiderweb of long crossing roads."""
    world = World(
        generate_terrain(60, 20, 1),
        (Settlement(0, "A", 5, 10), Settlement(1, "B", 30, 10), Settlement(2, "C", 55, 10)),
    )
    assert gabriel_edges(world) == [(0, 1), (1, 2)]


def test_single_settlement_has_no_roads():
    world = generate_world(settlements=1, seed=3)
    assert generate_roads(world).routes == {}


# --------------------------------------------------------- drawing elsewhere

def test_the_overlay_covers_every_road_tile_as_plain_data():
    """Another renderer should be able to draw the roads without importing
    anything from this package."""
    import json

    from colonysim.roads import road_overlay

    world = generate_world(seed=7)
    network = generate_roads(world)
    overlay = road_overlay(network)

    assert len(overlay) == len(network.tiles)
    assert {(t["x"], t["y"]) for t in overlay} == set(network.tiles)
    json.dumps(overlay)  # must not raise


def test_links_give_one_line_per_route_between_real_settlements():
    import json

    from colonysim.roads import road_links

    world = generate_world(seed=7)
    network = generate_roads(world)
    links = road_links(network, world)

    assert len(links) == len(network.routes)
    for link in links:
        assert (link["x1"], link["y1"]) == world.settlements[link["from"]].pos
        assert (link["x2"], link["y2"]) == world.settlements[link["to"]].pos
        assert link["tier"] >= 1
    json.dumps(links)


def test_links_report_the_grade_a_route_reaches():
    """A minimap weights its lines by this, so it has to follow real wear."""
    from colonysim.roads import TIER_THRESHOLD, apply_traffic, road_links

    world = generate_world(seed=7)
    network = generate_roads(world)
    route = next(iter(network.routes.values()))

    before = {(l["from"], l["to"]): l["tier"] for l in road_links(network, world)}
    apply_traffic(network, route, TIER_THRESHOLD[3])
    after = {(l["from"], l["to"]): l["tier"] for l in road_links(network, world)}

    assert after[route.key] > before[route.key]
