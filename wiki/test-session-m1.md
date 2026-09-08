# Test Session: Milestone 1 in the real game

Checklist for the first joint run. Tick as we go; record surprises at the bottom.

## Before the session (user's machine)

- [ ] RimWorld 1.6 installed, with the Harmony mod from the Workshop (ID 2009463077) or GitHub.
- [ ] .NET 8 SDK installed (only needed if rebuilding; the tarball ships a compiled `AiRim.dll`).
- [ ] Python 3.11+ and `uv` installed.
- [ ] Project unpacked. Symlink or copy `mod/` into the RimWorld `Mods/` folder as `AiRim`.
  - Windows default: `C:\Program Files (x86)\Steam\steamapps\common\RimWorld\Mods\`
  - macOS: `~/Library/Application Support/Steam/steamapps/common/RimWorld/RimWorldMac.app/Mods/`
  - Linux: `~/.steam/steam/steamapps/common/RimWorld/Mods/`
- [ ] `cd orchestrator && uv sync --extra dev && uv run pytest` passes.

## Letting Claude watch

Run the orchestrator with `--publish`. Every 30 s it commits the live log and a state summary to the `telemetry` branch on GitHub (in a separate worktree, never touching `main`) and pushes. Claude polls that branch during the session. Your git credentials on this machine must be able to push to the repo.

```
uv run airim serve --publish
```

## Smoke test

1. `uv run airim serve --publish` and open http://127.0.0.1:7600/. Header dot should be red (no mod yet).
2. Launch RimWorld. Enable Harmony then AiRim in the mod list, restart.
3. Check the in-game log (Options → Development mode → log) for `[AiRim] patches applied`. Any red error mentioning AiRim: copy it.
4. Load or start a colony. Within a few seconds the dot should go green and pawn cards should appear.
5. Speed 1 for one in-game hour. Expect job_start/job_end in the ticker; interactions when pawns chat.
6. Click a pawn card. Drawer should show thoughts, traits, skills, relations.
7. Draft a colonist and undraft. Expect job events.
8. Dev mode → Debug actions → start a mental break on a pawn. Expect `mental_state`.
9. Dev mode → Incidents → trigger a trade caravan. Expect `incident` and `letter`, then a visitor card.
10. Dev mode → damage a pawn. Expect `hediff`.
11. Speed 3 for one in-game day. Watch for `dropped` events and any stutter.
12. Save, quit to menu, reload. Expect a fresh `hello` and the card grid to reset.

## Things to record

- Player.log path and any `[AiRim]` errors.
- Whether `job` labels on cards read well (they come from `JobDriver.GetReport`).
- Whether the `source` field on job_start is useful or always null.
- Snapshot size per 250 ticks with a 5–10 pawn colony (check the session log file size growth in `orchestrator/logs/`).
- Dubs Performance Analyzer numbers for the `AiRim` patch classes if installed.

## Known unknowns

- `Pawn_JobTracker.StartJob` also fires for queued and resumed jobs; expect some noise.
- `PlayLog.Add` covers social interactions but not combat log entries (those go to `BattleLog`). Fine for M1.
- Interaction text uses the initiator's point of view.
- Snapshots are per map; with multiple maps (caravans, Odyssey gravship) pawn ids stay unique but the dashboard doesn't group by map yet.

## Findings

(fill in during the session)

### Session 1, 2026-09-07 evening (user's Mac, RimWorld 1.6.4871 rev597)

- Mod loaded, connected, and streamed from a live colony ("Aurora", 3 colonists) with no errors. Telemetry branch publishing worked; Claude followed from the cloud session.
- Every event type fired within 10 minutes: job_start/job_end, interaction (chitchat), hediff (malnutrition), letter + incident (quest, trade caravan), pawn_snapshot with all fields, world_snapshot. Visitors from the caravan were classified `visitor` with their faction.
- No `dropped` or `malformed` events at speed 1–2 with 11 pawns.
- Bugs found: interaction text carried Unity `<color>` tags; letter text carried `(*Faction=...)` markup; job labels had a trailing period. Fixed by stripping markup in the mod (`Events.Clean`) and defensively in the dashboard.
- Observed: Goto and Wait_MaintainPosture jobs for arriving caravan pawns start and end on the same tick. Expected for lord-driven travel; noisy but harmless. Consider filtering same-tick pairs in M2.
- `source` on job_start is populated (e.g. `JobGiver_GotoTravelDestination`, `JobGiver_Work`) and useful.
- `relations` came back empty for all pawns; unverified whether the colony simply has none. Check with a pawn known to have family.
