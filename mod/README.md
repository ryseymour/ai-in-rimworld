# AiRim mod (RimWorld 1.6)

Observation-only mod. Streams pawn and colony events over TCP to the orchestrator.

## Build

Requires the .NET 8 SDK. No RimWorld install needed to compile: references come from the `Krafs.Rimworld.Ref` and `Lib.Harmony.Ref` NuGet packages.

```
cd mod/Source/AiRim
dotnet build -c Release
```

Output lands in `mod/1.6/Assemblies/AiRim.dll`.

## Install

Copy or symlink the `mod/` folder into your RimWorld `Mods/` directory (rename it to `AiRim` if you like). Enable Harmony and then AiRim in the mod list. Settings live under Options → Mod settings → AI in RimWorld (host, port, enabled, snapshot interval).

## Run

Start the orchestrator first, then the game. The mod reconnects with backoff, so order doesn't strictly matter.

```
cd orchestrator
uv run airim serve
```

Dashboard: http://127.0.0.1:7600/  Mod socket: 127.0.0.1:7601

## What it hooks

| Patch | Event |
|---|---|
| `Pawn_JobTracker.StartJob` / `EndCurrentJob` | `job_start`, `job_end` |
| `PlayLog.Add` (interactions) | `interaction` |
| `MentalStateHandler.TryStartMentalState` | `mental_state` |
| `Pawn_HealthTracker.AddHediff` | `hediff` |
| `Pawn.Kill` | `death` |
| `LetterStack.ReceiveLetter` | `letter` |
| `IncidentWorker.TryExecute` | `incident` |
| `GameComponentTick` every N ticks | `world_snapshot`, `pawn_snapshot` |

All game reads happen on the main thread. The socket lives on a background thread fed by a bounded queue; overflow is reported as a `dropped` event rather than stalling the game.

## Status

Compiles clean against 1.6.4871 with warnings as errors. Patch signatures verified by reflection against the reference assembly. **Not yet run inside the game.**
