"""The browser viewer: payloads, routes, and not falling over on a busy port."""
from __future__ import annotations

import json
import threading
import urllib.request

import pytest

from colonysim.server import (
    Clock,
    cargo_text,
    make_handler,
    serve_somewhere,
    state_payload,
    world_payload,
)
from colonysim.simulation import build_simulation


@pytest.fixture
def running():
    """A real server on an ephemeral port, so the routes are tested as served
    rather than by calling the handler directly."""
    sim = build_simulation(seed=23)
    while not sim.caravans:
        sim.step_day()

    clock = Clock(sim, days_per_second=0, limit=0)
    server = serve_somewhere("127.0.0.1", 0, make_handler(clock))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", sim, clock
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read()


def test_the_page_is_served(running):
    base, _, _ = running
    status, body = get(base + "/")
    assert status == 200
    assert b"<title>Colony trade</title>" in body


def test_the_world_is_sent_once_and_completely(running):
    base, sim, _ = running
    _, body = get(base + "/world")
    world = json.loads(body)

    assert world["width"] == sim.world.terrain.width
    assert len(world["kinds"]) == world["width"] * world["height"]
    assert len(world["settlements"]) == len(sim.world.settlements)


def test_state_puts_every_caravan_on_a_road_tile(running):
    base, sim, _ = running
    _, body = get(base + "/state")
    state = json.loads(body)

    assert state["day"] == sim.day
    assert state["caravans"], "this world should have traders out by now"
    for caravan in state["caravans"]:
        assert (caravan["x"], caravan["y"]) in sim.network.tiles


def test_unknown_paths_are_not_found(running):
    base, _, _ = running
    with pytest.raises(urllib.error.HTTPError) as err:
        get(base + "/nonsense")
    assert err.value.code == 404


def test_pausing_stops_the_days(running):
    base, sim, _ = running
    _, body = get(base + "/control?toggle=1")
    assert json.loads(body)["paused"] is True

    day = sim.day
    get(base + "/state")
    get(base + "/state")
    assert sim.day == day


def test_speed_can_be_set(running):
    base, _, clock = running
    _, body = get(base + "/control?speed=9")
    assert json.loads(body)["speed"] == 9.0
    assert clock.days_per_second == 9.0


def test_a_busy_port_falls_back_to_the_next_one():
    """The default port is a popular one, and the point of the viewer is that
    it just opens rather than making you clear a port first."""
    sim = build_simulation(seed=1)
    first = serve_somewhere("127.0.0.1", 0, make_handler(Clock(sim, 0, 0)))
    taken = first.server_address[1]
    try:
        second = serve_somewhere("127.0.0.1", taken, make_handler(Clock(sim, 0, 0)))
        assert second is not None
        assert second.server_address[1] != taken
        second.server_close()
    finally:
        first.server_close()


def test_the_clock_advances_only_when_time_has_passed():
    """Days come from the wall clock, not from requests, so every browser
    watching sees the same day and polling faster does not run the world
    faster. `last` is wound back here to stand in for time passing."""
    sim = build_simulation(seed=23)
    clock = Clock(sim, days_per_second=10, limit=0)

    clock.catch_up()
    assert sim.day == 0, "no time has passed, so no day should have run"

    clock.last -= 1.0
    clock.catch_up()
    assert sim.day == 10

    day = sim.day
    clock.catch_up()
    assert sim.day == day, "polling again without time passing changes nothing"


def test_the_clock_respects_its_day_limit():
    sim = build_simulation(seed=23)
    clock = Clock(sim, days_per_second=100, limit=3)
    for _ in range(5):
        clock.last -= 1.0
        clock.catch_up()
    assert sim.day == 3


def test_a_paused_clock_does_not_bank_up_days():
    """Unpausing after a long pause should not fast-forward a month."""
    sim = build_simulation(seed=23)
    clock = Clock(sim, days_per_second=10, limit=0)
    clock.paused = True

    clock.last -= 30.0
    clock.catch_up()
    assert sim.day == 0

    clock.paused = False
    clock.catch_up()
    assert sim.day == 0, "the paused stretch should not be owed back"


def test_cargo_reads_as_words():
    assert cargo_text({}) == ""
    assert cargo_text({"food": 0.1}) == ""
    assert cargo_text({"food": 12.4, "wood": 30.0}) == "30 wood, 12 food"


def test_a_hungry_colony_is_flagged_for_the_page():
    sim = build_simulation(seed=23)
    sim.trade_enabled = False
    sim.run(200)
    payload = state_payload(sim)
    assert any(c["hungry"] for c in payload["colonies"])


def test_world_payload_names_every_terrain_it_draws():
    sim = build_simulation(seed=23)
    kinds = set(world_payload(sim)["kinds"])
    assert kinds <= {"water", "plains", "forest", "rough"}
