# RimWorld Runtime Observation & Control — Modding Research

Research date: 2026-09-07. `rimworldwiki.com`, `ludeon.com`, and `steamdb.info` were blocked by the sandbox proxy, so claims sourced to them come from search snippets. One heavily used secondary source (`Dev-Jahn/rimworld-modding-reference`) self-describes as AI-generated and "may contain inaccuracies"; flagged where it is the only source.

---

## 1. Current version and DLC (as of Sept 2026)

| Fact | Source |
|---|---|
| Latest major version is **1.6**, released **July 11, 2025** with the **Odyssey** expansion (5th DLC). 1.6 was free; big performance improvements, reworked mapgen, flying animals. | [Ludeon: Odyssey out now](https://ludeon.com/blog/2025/07/the-rimworld-odyssey-expansion-is-out-now/), [Announcing Odyssey and 1.6](https://ludeon.com/blog/2025/06/announcing-odyssey-and-update-1-6/) |
| Point releases continue (RimRef NuGet tracks 1.6.4850 / 1.6.4871). | [NuGet Krafs.Rimworld.Ref](https://www.nuget.org/packages/Krafs.Rimworld.Ref) |
| 1.6 runs on **Unity 2022.3.35**. | [Wiki: Modding Tutorials](https://rimworldwiki.com/wiki/Modding_Tutorials) |
| Odyssey: gravship (mobile flying base), orbital/space maps. Mostly new map/travel systems, not new pawn-AI primitives. | [Gravship wiki](https://rimworldwiki.com/wiki/Gravship) |
| DLCs: Royalty, Ideology (precepts, roles, rituals), Biotech (mechanitors, `mechEnabledWorkTypes`; custom mech ThinkTrees must be patched by hand), Anomaly (entities, containment, Dark Research, psychic rituals), Odyssey. | [Ideology wiki](https://rimworldwiki.com/wiki/Ideology_(DLC)), [Mechanitor wiki](https://rimworldwiki.com/wiki/Mechanitor), [Anomaly wiki](https://rimworldwiki.com/wiki/Anomaly_(DLC)) |

**AI-relevant DLC impact:** each DLC adds ThinkTree nodes/JobGivers/WorkTypes. Mods that patch the `Humanlike` ThinkTree or `JobGiver_Work` must handle DLC-conditional defs (`LoadFolders.xml` `IfModActive` gating). Odyssey adds gravship/space maps that pawn-scanning code must treat as ordinary `Map` instances.

---

## 2. Runtime environment: DLL loading, .NET, Mono

| Fact | Source |
|---|---|
| Mods are folders under `Mods/`; `About/About.xml` (name, author, `packageId`, `supportedVersions`, `modDependencies`, `loadAfter/loadBefore`) is mandatory; `Assemblies/` DLLs load automatically; version folders `1.5/`, `1.6/`, `Common/` or `LoadFolders.xml` control per-version loading. | [Dev-Jahn mod-structure](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/02-modding-fundamentals/mod-structure.md), [Rimworld-Mods/Template](https://github.com/Rimworld-Mods/Template) |
| Entry points: a class extending `Verse.Mod` (instantiated after assembly load, before Defs; good for Harmony/settings) and `[StaticConstructorOnStartup]` static classes (run after Defs load). | [Dev-Jahn harmony-patching](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/02-modding-fundamentals/harmony-patching.md), [roxxploxx Harmony](https://github.com/roxxploxx/RimWorldModGuide/wiki/SHORTTUTORIAL:-Harmony) |
| Target framework: **.NET Framework 4.7.2** (`net472`). | [Wiki: Setting up a solution](https://rimworldwiki.com/wiki/Modding_Tutorials/Setting_up_a_solution), [krafs/RimRef](https://github.com/krafs/RimRef/blob/main/README.md) |
| References: `Assembly-CSharp.dll`, `UnityEngine*.dll` from `RimWorldWin64_Data/Managed`, or the **Krafs.Rimworld.Ref** NuGet reference assemblies (auto-updated daily). Harmony via `Lib.Harmony.Ref` NuGet. | [krafs/RimRef](https://github.com/krafs/RimRef), [HarmonyRimWorld](https://github.com/pardeike/HarmonyRimWorld) |
| Linux build without VS: `FrameworkPathOverride=.../lib/mono/4.7.2-api/ dotnet build X.csproj`. VS Code template builds + launches game with F5. | [Lobz tutorial lesson7](https://github.com/Lobz/modding-Rimworld-tutorial/blob/main/lesson7.md), [Rimworld-Mods/Template](https://github.com/Rimworld-Mods/Template) |
| Decompiling: ILSpy / dnSpy on `Assembly-CSharp.dll`; dated decompile at josh-m/RW-Decompile. | [jecrell gist](https://gist.github.com/jecrell/79299728f0a614875ff79995f6cc3c02), [RW-Decompile](https://github.com/josh-m/RW-Decompile) |

---

## 3. Harmony patching

| Fact | Source |
|---|---|
| Harmony injects Prefix/Postfix/Transpiler/Finalizer. Prefix runs before (return `false` skips original; discouraged for compat), Postfix after (`ref __result`), `__instance`, `___field` for private fields. `[HarmonyPriority]`, `[HarmonyBefore]/[HarmonyAfter]` order patches. | [Wiki: Harmony](https://rimworldwiki.com/wiki/Modding_Tutorials/Harmony), [Wiki: HarmonyTranspiler](https://rimworldwiki.com/wiki/Modding_Tutorials/HarmonyTranspiler), [roxxploxx Harmony](https://github.com/roxxploxx/RimWorldModGuide/wiki/SHORTTUTORIAL:-Harmony) |
| Canonical setup: `[StaticConstructorOnStartup] static class Patches { static Patches(){ new Harmony("author.modname").PatchAll(); } }`. | same |
| Do **not** bundle `0Harmony.dll`; depend on the Harmony Workshop mod (ID 2009463077, packageId `brrainz.harmony`) via `modDependencies`. | [pardeike/HarmonyRimWorld](https://github.com/pardeike/HarmonyRimWorld) |
| Reference corpus of ~180 patches: Humanoid Alien Races `HarmonyPatches`. | [Wiki: Harmony](https://rimworldwiki.com/wiki/Modding_Tutorials/Harmony) |

**Observation hooks worth patching:** `Pawn_JobTracker.StartJob`, `Pawn_JobTracker.EndCurrentJob`, `Pawn_JobTracker.DetermineNextJob`/`TryFindAndStartJob`, `ThinkNode.TryIssueJobPackage`, `JobGiver_Work.TryIssueJobPackage`, `JobDriver.MakeNewToils`. Verify names against the current 1.6 `Assembly-CSharp.dll`. [RW-Decompile JobGiver_Work.cs](https://github.com/josh-m/RW-Decompile/blob/master/RimWorld/JobGiver_Work.cs), [Dev-Jahn job-system](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/03-gameplay-systems/job-system.md)

---

## 4. Pawn AI decision-making: ThinkTrees, JobGivers, priorities

| Fact | Source |
|---|---|
| "The entirety of RW pawn behavior can be reduced to 2 characteristics: whether any given JobGiver/WorkGiver is valid for that pawn, and the order in which these Givers are checked" — that order is the pawn's **ThinkTree**. Pawn executes the first valid Job returned. | [CBornholdt AI Tutorial Part 1](https://github.com/CBornholdt/RimWorld-AI-Tutorial/wiki/Part-1---Introduction) |
| `ThinkTreeDef` XML: `defName`, `thinkRoot` (a `ThinkNode`), optional `insertTag` + `insertPriority`. Root evaluates subnodes producing a `ThinkResult` (Job + source node). | [roxxploxx How Pawns Think](https://github.com/roxxploxx/RimWorldModGuide/wiki/SHORTTUTORIAL:-How-Pawns-Think) |
| Node types: `ThinkNode_Priority` (first valid child wins), `ThinkNode_PrioritySorter`, `ThinkNode_Random`, `ThinkNode_Subtree`, `ThinkNode_SubtreesByTag`, `ThinkNode_Conditional*`, `ThinkNode_JobGiver` subclasses implementing `TryGiveJob(Pawn)` → `Job` or null, plus `GetPriority(Pawn)`. | [CBornholdt Part 1](https://github.com/CBornholdt/RimWorld-AI-Tutorial/wiki/Part-1---Introduction), [Dev-Jahn ai-behavior](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/03-gameplay-systems/ai-behavior.md) |
| Each pawn has two trees: a **ConstantThinkTree** (evaluated every ~30 ticks for emergencies; can interrupt the current job) and a **MainThinkTree** (evaluated when a new job is needed). Effective order: constant tree → mental states → Lord duties → player-ordered jobs → work jobs (Work tab priorities 1–4) → idle/joy/wander. *(Dev-Jahn only; verify.)* | [Dev-Jahn ai-behavior](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/03-gameplay-systems/ai-behavior.md) |
| Work: `JobGiver_Work.TryIssueJobPackage` iterates `WorkGiver`s in priority order, calls `NonScanJob()` or scans `PotentialWorkThingRequest`/cells, ranks, checks reachability, then `JobOnThing()`/`JobOnCell()`. | [RW-Decompile JobGiver_Work.cs](https://github.com/josh-m/RW-Decompile/blob/master/RimWorld/JobGiver_Work.cs) |
| Duties/Lords: `Lord` → `LordJob` (StateGraph) → `LordToil` (assigns `PawnDuty`) → `DutyDef` with its own `thinkNode`. `pawn.mindState.duty`, `pawn.MentalState`. | [CBornholdt Part 1](https://github.com/CBornholdt/RimWorld-AI-Tutorial/wiki/Part-1---Introduction) |
| Insertion points (`<insertTag>`): `Humanlike_PostMentalState`, `Humanlike_PostDuty`, `Humanlike_PreMain`, `Humanlike_PostMain`, `Animal_PreMain`, `Animal_PreWander`. Put cheap validity checks first. | [CBornholdt Part 1](https://github.com/CBornholdt/RimWorld-AI-Tutorial/wiki/Part-1---Introduction), [roxxploxx How Pawns Think](https://github.com/roxxploxx/RimWorldModGuide/wiki/SHORTTUTORIAL:-How-Pawns-Think) |
| Alternative: XML `PatchOperationAdd` on `/Defs/ThinkTreeDef[defName="Humanlike"]/thinkRoot/subNodes`. | [Wiki: PatchOperations](https://rimworldwiki.com/wiki/Modding_Tutorials/PatchOperations) |

---

## 5. Adding custom jobs / behaviours

| Fact | Source |
|---|---|
| Pipeline: ThinkTree → JobGiver/WorkGiver → `Job` (JobDef + targets) → `JobDriver` → `Toil`s. | [roxxploxx How Pawns Think](https://github.com/roxxploxx/RimWorldModGuide/wiki/SHORTTUTORIAL:-How-Pawns-Think), [Ludeon forum: ThinkTree to Toil](https://ludeon.com/forums/index.php?topic=16405.0) |
| `JobDef` XML: `defName`, `driverClass`, `reportString`, `casualInterruptible`, `suspendable`, `playerInterruptible`. Reference via `[DefOf]`. | [roxxploxx Jobs and Work](https://github.com/roxxploxx/RimWorldModGuide/wiki/SHORTTUTORIAL:-Jobs-and-Work) |
| `JobDriver`: override `TryMakePreToilReservations` and `MakeNewToils()` yielding Toils (`Toils_Goto`, `Toils_General.Wait`, `Toils_Haul.*`, custom `ToilMaker.MakeToil` with `initAction`/`tickAction`, `FailOn*`). | [Dev-Jahn job-system](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/03-gameplay-systems/job-system.md), [Wiki: Example Mending Job](https://rimworldwiki.com/wiki/Modding_Tutorials/Code_MendingJob) |
| Work-tab integration: `WorkTypeDef` and `WorkGiverDef` pointing at a `WorkGiver_Scanner`. | same |
| **Forcing a job from code:** `Job j = JobMaker.MakeJob(def, target); pawn.jobs.StartJob(j, JobCondition.InterruptOptional)` or `pawn.jobs.TryTakeOrderedJob(j)`, `pawn.jobs.jobQueue.EnqueueFirst(j)`, `pawn.jobs.EndCurrentJob(JobCondition.InterruptForced)`. Mental states: `pawn.mindState.mentalStateHandler.TryStartMentalState(...)`. Group AI: `LordMaker.MakeNewLord(...)`. | [Dev-Jahn ai-behavior](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/03-gameplay-systems/ai-behavior.md) |
| Right-click orders: `FloatMenuOptionProvider` (1.6). | [Wiki: Example Mending Job](https://rimworldwiki.com/wiki/Modding_Tutorials/Code_MendingJob) |

---

## 6. Tick model and game speed

| Fact | Source |
|---|---|
| 1 tick = 1/60 s at Normal speed → **60 tps**. `Tick()` every tick, `TickRare()` every 250 ticks (~4.2 s), `TickLong()` every 2000 ticks (~33 s). Throttle idiom: `IsHashIntervalTick`. | [Wiki: Time](https://rimworldwiki.com/wiki/Time), [HugsLib Custom Tick Scheduling](https://github.com/UnlimitedHugs/RimworldHugsLib/wiki/Custom-Tick-Scheduling) |
| Target rates: 1x = 60 tps, 2x = 180, 3x = 360, 4x (dev Ultrafast) = 900. Game runs as many `TickManager.DoSingleTick()` per Unity frame as needed. | [Dubs Performance Analyzer wiki](https://github.com/Dubwise56/Dubs-Performance-Analyzer/wiki), [TicksPerSecond](https://github.com/sparr/rimworld-mod-TicksPerSecond) |
| **1.6 Variable Tick Rate (VTR):** pawns far from camera tick non-time-sensitive systems less often, down to ~4 Hz; Things use delta-based `TickInterval(int delta)`. Wiki page "RimWorld 1.6 Mod Updates" is the migration guide. | [Wiki: 1.6 Mod Updates](https://rimworldwiki.com/wiki/Modding_Tutorials/RimWorld_1.6_Mod_Updates), [Slower Pawn Tick Rate mod](https://steamcommunity.com/sharedfiles/filedetails/?id=3524116050) |
| Mod-level hooks: `GameComponent`/`MapComponent`/`WorldComponent` `*Tick()`/`*Update()` (Update = per Unity frame, runs while paused; Tick = per game tick). | [HugsLib Custom Tick Scheduling](https://github.com/UnlimitedHugs/RimworldHugsLib/wiki/Custom-Tick-Scheduling) |
| Vanilla sim is single-threaded; RimThreaded exists but is invasive/unstable. | [RimThreaded](https://steamcommunity.com/sharedfiles/filedetails/?id=2222907981) |

---

## 7. Exposing game state externally

### Threading constraints
| Fact | Source |
|---|---|
| Unity APIs and essentially all game state (`Find.*`, `pawn.jobs/needs/health/mindState`, `map.*`, `DefDatabase`, `GenSpawn`, `Scribe_*`, `Messages`, `Find.WindowStack`) must be touched only on the main thread. Safe off-thread: network I/O, file I/O, pure compute, concurrent collections, `Log.*`. | [Dev-Jahn threading-async](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/08-advanced-topics/threading-async.md), [HarmonyRimWorld issue #7](https://github.com/pardeike/HarmonyRimWorld/issues/7) |
| Pattern: snapshot on main thread → `Task.Run` → `ConcurrentQueue<Action>` → drain in `GameComponent.GameComponentUpdate/Tick` → re-validate `pawn.Spawned && !pawn.Dead`. `LongEventHandler.ExecuteWhenFinished(Action)` is the built-in main-thread marshaller. | same |

### Existing external-access mods (prior art)
| Project | What it does | Source |
|---|---|---|
| **RimBridgeServer** (pardeike, MIT, 1.6) | MCP bridge inside RimWorld (port 5174, token auth). Inspect pawns/cells/UI/alerts/letters, draft, debug actions, designators, zones, pause/speed/step N ticks (`RunForTicksAsync`), screenshots, profiler, JSON/Lua scripting; extensible via `RimBridgeServer.Sdk` NuGet. | [pardeike/RimBridgeServer](https://github.com/pardeike/RimBridgeServer) |
| **RimAPI** (GPLv3, 1.5–1.6) | REST + SSE on `http://localhost:8765/`, 120+ endpoints, non-blocking with caching. | [IlyaChichkov/RIMAPI](https://github.com/IlyaChichkov/RIMAPI) |
| **RimMind-Core** | "All AI requests run on background threads; main thread only processes callbacks." | [RimMind-Core](https://github.com/RimWorld-RimMind-Mod/RimWorld-RimMind-Mod-Core) |
| RimWorld Together / Zetrith Multiplayer | Client/server networking; MP's Sync/determinism docs show what state is safe to mutate when. | [Rimworld-Together](https://github.com/RimWorld-Together/Rimworld-Together) |

### File logging
`Verse.Log.*` writes to the in-game console and Unity's `Player.log` (`%LOCALAPPDATA%Low\Ludeon Studios\RimWorld by Ludeon Studios\Player.log`; Linux `~/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/`). Uncapped spam bloats it to GBs. Plain `System.IO` writes from a background thread are fine for custom telemetry. [Dev-Jahn debugging](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/08-advanced-topics/debugging.md)

---

## 8. Dev tooling

| Tool | Notes | Source |
|---|---|---|
| **Development mode** | Debug log, tweak values, debug actions, inspector, dev palette, god mode. "Toggle job logging" and "Draw pawn debug" diagnose pawn AI; the inspector shows current job/think node. | [Wiki: Development mode](https://rimworldwiki.com/wiki/Development_mode), [Wiki: Testing mods](https://rimworldwiki.com/wiki/Modding_Tutorials/Testing_mods) |
| **Custom DebugActions** | `[DebugAction("Category","Label", actionType = ..., allowedGameStates = ...)]` on a static method. | [Wiki: DebugActions](https://rimworldwiki.com/wiki/Modding_Tutorials/DebugActions) |
| **Dubs Performance Analyzer** | Per-method/tick profiler; can profile Harmony patch classes. | [Dubwise56 repo](https://github.com/Dubwise56/Dubs-Performance-Analyzer) |
| Better Log, Visual Exceptions, TDBug, HugsLib | Log/exception UX. | [Dev-Jahn debugging](https://github.com/Dev-Jahn/rimworld-modding-reference/blob/main/08-advanced-topics/debugging.md) |
| Docs & community | Wiki Modding Tutorials hub; RimWorld Discord `#mod-development`; Ludeon forums; roxxploxx and CBornholdt guides; Dev-Jahn reference. | [Wiki hub](https://rimworldwiki.com/wiki/Modding_Tutorials), [Discord](https://discord.com/invite/rimworld), [roxxploxx](https://github.com/roxxploxx/RimWorldModGuide/wiki), [Dev-Jahn](https://github.com/Dev-Jahn/rimworld-modding-reference) |

---

## 9. Practical architecture recommendation (synthesis)

1. **Build**: SDK-style csproj, `net472`, `Krafs.Rimworld.Ref` + `Lib.Harmony.Ref`; output to `<mod>/1.6/Assemblies/`; depend on `brrainz.harmony`.
2. **Observe**: Harmony Postfix on `Pawn_JobTracker.StartJob/EndCurrentJob` and `ThinkNode_JobGiver.TryIssueJobPackage` to log which node produced which Job; snapshot into plain DTOs on the main thread.
3. **Control**: from the main thread, `JobMaker.MakeJob` + `pawn.jobs.StartJob/TryTakeOrderedJob`, `Find.TickManager` for pause/speed, or insert a `ThinkTreeDef` with `insertTag=Humanlike_PreMain` whose JobGiver consults an externally fed command queue.
4. **Transport**: `HttpListener`/TCP on a background thread (RimAPI/RimBridgeServer precedent), `ConcurrentQueue` drained in `GameComponent.GameComponentUpdate()`; never touch game objects off-thread.
5. **Timing**: respect 1.6 VTR; assume 60/180/360/900 tps targets.
