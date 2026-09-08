# Backlog

Tasks, ideas, and work items for the AI in Rimworld project.

## Milestone 1: observation layer (in progress)

- [x] Mod build setup (net472, RimRef, Harmony ref).
- [x] Observation patches: jobs, interactions, mental states, hediffs, deaths, letters, incidents.
- [x] Periodic world and pawn snapshots.
- [x] Background-thread TCP transport with bounded queue.
- [x] Orchestrator: receiver, event log, state, dashboard, replay, tests.
- [ ] **Run the mod in RimWorld 1.6 and confirm events arrive.** Needs a machine with the game.
- [ ] Check Player.log for exceptions from the patches; profile with Dubs Performance Analyzer.
- [ ] Record a real session log and add it as a fixture.
- [ ] Capture think-node source on job_start via the `jobGiver` parameter of StartJob.
- [ ] Add dialogue-relevant events: recruit/tame attempts, trades, arrests, romance outcomes.

## Milestone 2: first minds (not started)

- Design the conversation system: agent↔agent, agent↔player, group discussion, all on one machinery.
- Design the user-driven player pawn: how it's created, how the user talks through it, what overseer powers remain.
- Design visitor agents: goals, allowed actions beyond vanilla, lifecycle.
- Action channel back into the game (orchestrator → mod), protocol modeled on the Neuro SDK.
- Cost model: estimate tokens per pawn per in-game day.

## Other

- Evaluate RIMAPI and RimBridgeServer as alternatives or complements to our bridge.
- Create the GitHub repo and push.
