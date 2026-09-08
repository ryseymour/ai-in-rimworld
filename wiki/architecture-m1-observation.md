# Milestone 1: Observation Layer

Goal: see everything the game exposes about pawns, live, without any model calls. Every later milestone builds on this pipe.

## Components

```
RimWorld (Unity, main thread)                 Orchestrator (Python)
┌──────────────────────────────┐   TCP/JSONL  ┌──────────────────────────┐
│ Harmony patches ──► snapshot │ ───────────► │ receiver ──► event log   │
│ GameComponent    ──► queue   │              │          ──► state store │
│ background thread ──► socket │ ◄─────────── │ dashboard (HTTP + WS)    │
└──────────────────────────────┘  (later:     └──────────────────────────┘
                                   actions)             │
                                                        ▼
                                                  browser page
```

### RimWorld mod (`mod/`)

- **Target:** RimWorld 1.6, `net472`, references via `Krafs.Rimworld.Ref` and `Lib.Harmony.Ref` NuGet packages. Depends on the Harmony Workshop mod at runtime.
- **Entry:** `AiRimMod : Verse.Mod` (settings: host, port, enabled) plus `[StaticConstructorOnStartup]` class that runs `Harmony.PatchAll()`.
- **Patches (observe only):**
  - `Pawn_JobTracker.StartJob` postfix → `job_start` event (pawn, job def, target, source think node if available).
  - `Pawn_JobTracker.EndCurrentJob` postfix → `job_end` event (pawn, job def, condition).
  - `PlayLog.Add` postfix → `interaction` event (initiator, recipient, interaction def, rendered text).
  - `Pawn_MentalStateTracker.StartMentalState` postfix → `mental_state` event.
  - `Pawn_HealthTracker.AddHediff` postfix → `hediff` event (filtered to notable ones).
  - `Pawn.Kill` postfix → `death` event.
  - `LetterStack.ReceiveLetter` postfix → `letter` event (label, text).
  - `IncidentWorker.TryExecute` postfix → `incident` event.
- **Periodic snapshot:** `GameComponent.GameComponentTick` every 250 ticks emits `pawn_snapshot` for each colonist and present non-colonist humanlike: name, faction, position, current job, needs (food, rest, joy, mood), mood thoughts top 5, health summary, skills, traits, relations summary. Plus `world_snapshot`: tick, date string, weather, season, colony wealth, pawn counts.
- **Transport:** background thread owns a `TcpClient` to the orchestrator. Events are JSON objects, newline-delimited. A `ConcurrentQueue<string>` sits between main thread (producer) and socket thread (consumer). Reconnect with backoff. Never block the main thread on the socket; drop events if the queue exceeds a cap and emit one `dropped` event.
- **Serialization:** hand-rolled minimal JSON writer to avoid dependency issues under Mono. Newtonsoft ships with RimWorld but version conflicts are common; avoid for now.
- **Thread rule:** game objects are read only inside patches and `GameComponentTick`. The socket thread only ever sees strings.

### Orchestrator (`orchestrator/`)

- **Python 3.11+, `uv` managed.** Dependencies: `aiohttp` (HTTP + WebSocket server). No model SDKs yet.
- **Receiver:** asyncio TCP server on `127.0.0.1:7601`. Reads JSONL, stamps receive time, appends to `logs/<session>.jsonl`, updates in-memory state (`pawns: {id: latest snapshot}`, `world`, ring buffer of last N events).
- **Dashboard:** aiohttp on `127.0.0.1:7600`. `GET /` serves a single-page HTML app. `GET /api/state` returns current state. `WS /ws` pushes every event as it arrives. The page shows a pawn grid (cards with mood, job, needs), an event ticker, and a per-pawn detail drawer with the recent event history.
- **Replay:** `python -m airim.replay logs/x.jsonl --speed 10` feeds a log back through the same pipeline so the dashboard can be developed without the game running.

## Event schema (v0)

Every message: `{"v":0,"t":<game tick>,"ts":<unix ms>,"type":<string>,...}`.

| type | fields |
|---|---|
| `hello` | `mod_version`, `game_version`, `map_id` |
| `world_snapshot` | `date`, `season`, `weather`, `wealth`, `colonists`, `visitors`, `hostiles` |
| `pawn_snapshot` | `id`, `name`, `faction`, `kind` (colonist/visitor/prisoner/hostile/animal), `pos`, `job`, `needs{}`, `mood`, `thoughts[]`, `health`, `skills{}`, `traits[]`, `relations[]` |
| `job_start` / `job_end` | `pawn`, `job`, `target`, `source`, `condition` (end only) |
| `interaction` | `initiator`, `recipient`, `def`, `text` |
| `mental_state` | `pawn`, `state`, `reason` |
| `hediff` | `pawn`, `def`, `part`, `severity` |
| `death` | `pawn`, `cause`, `killer` |
| `letter` | `label`, `text`, `def` |
| `incident` | `def`, `label` |
| `dropped` | `count` |

Pawn `id` is `thingIDNumber`; stable within a save.

## Out of scope for M1

Model calls, actions back into the game, player pawn control, visitor logic. M1 is done when the dashboard shows a live colony and a replayed log looks the same.

## Verification plan

1. Unit: Python receiver parses a fixture log; dashboard state endpoint matches.
2. Build: mod compiles against RimRef 1.6 with zero warnings.
3. Manual: load mod in RimWorld 1.6 dev mode, start a colony, confirm events arrive and the dashboard updates. Check the Player.log for exceptions.
4. Perf: Dubs Performance Analyzer shows the patches under 0.05 ms per call.
