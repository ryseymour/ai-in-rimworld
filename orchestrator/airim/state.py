"""In-memory colony state built from the event stream."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

Event = dict[str, Any]

SNAPSHOT_TYPES = {"pawn_snapshot", "world_snapshot"}


@dataclass
class ColonyState:
    """Latest known state plus a bounded history of events."""

    world: Event = field(default_factory=dict)
    pawns: dict[int, Event] = field(default_factory=dict)
    hello: Event = field(default_factory=dict)
    recent: deque[Event] = field(default_factory=lambda: deque(maxlen=500))
    pawn_history: dict[int, deque[Event]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    last_event_at: float = 0.0

    def apply(self, ev: Event) -> None:
        t = ev.get("type", "unknown")
        self.counts[t] = self.counts.get(t, 0) + 1
        self.last_event_at = time.time()

        if t == "hello":
            self.hello = ev
            self.pawns.clear()
        elif t == "world_snapshot":
            self.world = ev
        elif t == "pawn_snapshot":
            self.pawns[int(ev["id"])] = ev
        elif t == "death":
            pid = ev.get("pawn")
            if pid in self.pawns:
                self.pawns[pid]["dead"] = True

        if t not in SNAPSHOT_TYPES:
            self.recent.append(ev)
            for key in ("pawn", "initiator", "recipient"):
                pid = ev.get(key)
                if isinstance(pid, int):
                    self.pawn_history.setdefault(pid, deque(maxlen=100)).append(ev)

    def snapshot(self) -> dict[str, Any]:
        return {
            "hello": self.hello,
            "world": self.world,
            "pawns": list(self.pawns.values()),
            "recent": list(self.recent),
            "counts": self.counts,
            "last_event_at": self.last_event_at,
        }

    def history_for(self, pawn_id: int) -> list[Event]:
        return list(self.pawn_history.get(pawn_id, ()))
