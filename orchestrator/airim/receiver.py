"""TCP JSONL receiver for the RimWorld mod."""
from __future__ import annotations

import asyncio
import logging

from .bus import EventBus, parse_line

log = logging.getLogger(__name__)


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, bus: EventBus) -> None:
    peer = writer.get_extra_info("peername")
    log.info("mod connected from %s", peer)
    await bus.publish({"type": "mod_connected", "peer": str(peer)})
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            ev = parse_line(line)
            if ev is not None:
                await bus.publish(ev)
    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        log.info("mod disconnected from %s", peer)
        await bus.publish({"type": "mod_disconnected", "peer": str(peer)})
        writer.close()


async def serve(bus: EventBus, host: str = "127.0.0.1", port: int = 7601) -> asyncio.AbstractServer:
    server = await asyncio.start_server(lambda r, w: _handle(r, w, bus), host, port)
    log.info("receiver listening on %s:%d", host, port)
    return server
