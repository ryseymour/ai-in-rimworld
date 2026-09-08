"""Fan-out of events to subscribers (dashboard websockets, loggers)."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from .state import ColonyState, Event

Subscriber = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self, state: ColonyState, log_path: Path | None = None) -> None:
        self.state = state
        self.log_path = log_path
        self._subs: set[Subscriber] = set()
        self._log = log_path.open("a", encoding="utf-8") if log_path else None
        self._lock = asyncio.Lock()

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.add(fn)

    def unsubscribe(self, fn: Subscriber) -> None:
        self._subs.discard(fn)

    async def publish(self, ev: Event) -> None:
        ev.setdefault("rx", int(time.time() * 1000))
        self.state.apply(ev)
        if self._log:
            self._log.write(json.dumps(ev, separators=(",", ":")) + "\n")
            self._log.flush()
        dead: list[Subscriber] = []
        for fn in list(self._subs):
            try:
                await fn(ev)
            except Exception:  # noqa: BLE001 - a bad subscriber must not stop the bus
                dead.append(fn)
        for fn in dead:
            self._subs.discard(fn)

    def close(self) -> None:
        if self._log:
            self._log.close()
            self._log = None


def parse_line(line: bytes | str) -> Event | None:
    """Parse one JSONL line; returns None for blank or malformed input."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    if not line:
        return None
    try:
        ev: Any = json.loads(line)
    except json.JSONDecodeError:
        return {"type": "malformed", "raw": line[:500]}
    if not isinstance(ev, dict) or "type" not in ev:
        return {"type": "malformed", "raw": line[:500]}
    return ev
