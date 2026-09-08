"""HTTP + WebSocket dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web, WSMsgType

from .bus import EventBus
from .state import Event

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def build_app(bus: EventBus) -> web.Application:
    app = web.Application()
    sockets: set[web.WebSocketResponse] = set()

    async def index(_: web.Request) -> web.Response:
        return web.FileResponse(STATIC / "index.html")

    async def state(_: web.Request) -> web.Response:
        return web.json_response(bus.state.snapshot())

    async def pawn(request: web.Request) -> web.Response:
        pid = int(request.match_info["id"])
        p = bus.state.pawns.get(pid)
        if p is None:
            raise web.HTTPNotFound()
        return web.json_response({"pawn": p, "history": bus.state.history_for(pid)})

    async def ws(request: web.Request) -> web.WebSocketResponse:
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(request)
        sockets.add(sock)
        await sock.send_str(json.dumps({"type": "state", "state": bus.state.snapshot()}))
        try:
            async for msg in sock:
                if msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
        finally:
            sockets.discard(sock)
        return sock

    async def broadcast(ev: Event) -> None:
        if not sockets:
            return
        data = json.dumps(ev)
        await asyncio.gather(*(s.send_str(data) for s in list(sockets)), return_exceptions=True)

    bus.subscribe(broadcast)
    app.router.add_get("/", index)
    app.router.add_get("/api/state", state)
    app.router.add_get("/api/pawn/{id}", pawn)
    app.router.add_get("/ws", ws)
    return app


async def serve(bus: EventBus, host: str = "127.0.0.1", port: int = 7600) -> web.AppRunner:
    runner = web.AppRunner(build_app(bus))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("dashboard at http://%s:%d/", host, port)
    return runner
