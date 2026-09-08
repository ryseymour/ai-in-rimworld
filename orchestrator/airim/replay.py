"""Feed a recorded JSONL log back through the bus."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .bus import EventBus, parse_line


async def replay(bus: EventBus, path: Path, speed: float = 10.0, loop: bool = False) -> None:
    """Replay events using recorded receive timestamps scaled by `speed`."""
    while True:
        prev_rx: int | None = None
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                ev = parse_line(line)
                if ev is None:
                    continue
                rx = ev.get("rx")
                if prev_rx is not None and isinstance(rx, int) and speed > 0:
                    delay = max(0, rx - prev_rx) / 1000 / speed
                    await asyncio.sleep(min(delay, 5.0))
                if isinstance(rx, int):
                    prev_rx = rx
                ev.pop("rx", None)
                await bus.publish(ev)
        if not loop:
            break
