# Backlog

Tasks, ideas, and work items for the AI in Rimworld project.

**2026-09-18 pivot:** the RimWorld mod is paused; the project now runs on the standalone ascii colony sim (`~/ascii-colony` on Ryan's Mac, not on GitHub). Trade, roads, wildlife and stewards are built as a portable module in `sim/colonysim/` here. See `wiki/project-direction.md` and `wiki/design-inter-colony-trade.md`.

## Colony sim (current)

- [x] Procedural roads between settlements (`roads.py`, `terrain.py`).
- [x] Storage, prices, currency, traders moving goods (`storage.py`, `trade.py`, `money.py`).
- [x] Wildlife: dens, hazards, raids, guards; traders route around danger (`wildlife.py`).
- [x] Stewards: per-colony agent setting prices, reserves, labour (`steward.py`).
- [x] Browser map of caravans on the roads (`server.py`, port 7700) and terminal watcher.
- [x] Road network exposed as JSON-safe data for other renderers.
- [x] Lift `sim/colonysim/` into `~/ascii-colony` (vendored 2026-09-19 by the local session; caravans, wildlife, and steward trade dials live in the game).
- [ ] Milestone 4 of the trade design: agent-driven traders with memory and negotiation.
- [ ] Put `~/ascii-colony` on GitHub so cloud sessions can read and change it.
- [ ] Pawn minds: per-pawn agents with persona, memory, dialogue (the original direction, now on the sim).
- [ ] Player character the user drives and talks through.

## RimWorld mod (paused)

Milestone 1, the observation layer, is done and verified in-game (sessions 1 and 2). Kept for when the RimWorld path is picked up again.

- [ ] Push the local mod changes seen on the telemetry branch on 2026-09-18 (`thought` events, `day`/`hour` fields); they are not in this repo.
- [ ] Check Player.log for exceptions from the patches; profile with Dubs Performance Analyzer.
- [ ] Record a real session log and add it as a fixture.
- [ ] Add dialogue-relevant events: recruit/tame attempts, trades, arrests, romance outcomes.
- [ ] Action channel back into the game (orchestrator → mod), protocol modeled on the Neuro SDK.
- [ ] Evaluate RIMAPI and RimBridgeServer as alternatives or complements to our bridge.
