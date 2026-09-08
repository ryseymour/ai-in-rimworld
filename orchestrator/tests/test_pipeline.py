import asyncio
import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from airim.bus import EventBus, parse_line
from airim.dashboard import build_app
from airim.receiver import serve as serve_receiver
from airim.replay import replay
from airim.state import ColonyState

FIX = Path(__file__).parent / "fixtures" / "sample.jsonl"


def test_parse_line_handles_garbage():
    assert parse_line(b"\n") is None
    assert parse_line(b"not json")["type"] == "malformed"
    assert parse_line(b'{"no":"type"}')["type"] == "malformed"
    assert parse_line(b'{"type":"x"}') == {"type": "x"}


async def test_replay_builds_state(tmp_path):
    bus = EventBus(ColonyState(), tmp_path / "out.jsonl")
    await replay(bus, FIX, speed=0)
    bus.close()
    s = bus.state.snapshot()
    assert s["world"]["date"] == "6th of Aprimay, 5500"
    assert {p["id"] for p in s["pawns"]} == {101, 102, 103, 201}
    assert bus.state.pawns[101]["dead"] is True
    assert bus.state.history_for(101)[-1]["type"] == "death"
    assert s["counts"]["interaction"] == 1
    # log round-trips
    logged = [json.loads(l) for l in (tmp_path / "out.jsonl").read_text().splitlines()]
    assert len(logged) == sum(1 for l in FIX.read_text().splitlines() if l.strip())
    assert all("rx" in e for e in logged)


async def test_receiver_to_dashboard():
    bus = EventBus(ColonyState())
    srv = await serve_receiver(bus, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]

    async with TestClient(TestServer(build_app(bus))) as client:
        ws = await client.ws_connect("/ws")
        first = json.loads((await ws.receive()).data)
        assert first["type"] == "state"

        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(FIX.read_bytes())
        await w.drain()
        w.close()

        seen = []
        while len(seen) < 3:
            msg = await asyncio.wait_for(ws.receive(), 5)
            seen.append(json.loads(msg.data)["type"])
        assert seen[0] == "mod_connected"
        assert "hello" in seen

        await asyncio.sleep(0.2)
        resp = await client.get("/api/state")
        state = await resp.json()
        assert len(state["pawns"]) == 4
        resp = await client.get("/api/pawn/103")
        body = await resp.json()
        assert body["pawn"]["name"] == "Cyn"
        assert any(e["type"] == "mental_state" for e in body["history"])
        assert (await client.get("/api/pawn/999")).status == 404
        await ws.close()
    srv.close()
    await srv.wait_closed()
