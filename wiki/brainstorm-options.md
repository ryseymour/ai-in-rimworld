# Brainstorm: How AI Agents Could Live in RimWorld (and How We Watch Them)

> **Decision recorded:** see `project-direction.md`. The project is Option 1 + Option 3 + Option 5, plus a user-driven player pawn.

Date: 2026-09-07. Draws on the three reports in `resources/`. Nothing here is decided yet.

## Framing: two axes

Every option is a point on two axes.

**Axis 1: What the agent *is*.**
- **A. Narrator / commentator.** Watches the colony and talks about it. Zero control. (RimGPT, Tales from the RimWorld.)
- **B. Storyteller.** Chooses the incidents and events the colony faces. Controls the world, not the pawns. (Claude Storyteller, RimAI.)
- **C. Overseer / player.** Plays the colony the way a human does: work priorities, zones, drafting, research. One brain for the whole colony. (rimworld-ai-manager, RimMolt, RLE.)
- **D. Inhabitant.** One agent per pawn, or per notable pawn. Each has a persona, memory, goals, and makes its own choices inside vanilla rules. The Smallville model.
- **E. Society.** Many inhabitants who talk to each other, form factions, and produce emergent story. Project Sid at RimWorld scale.

**Axis 2: How deep the control goes.**
- **Level 0: Voice only.** Dialogue bubbles, thoughts, journal entries. The game's AI still decides every job. (RimTalk.)
- **Level 1: Nudges.** Agent adjusts mood, opinions, relationships, or triggers vanilla interactions (recruit, romance, insult). (RimChat Word to Actions, RimTalk Expand Actions.)
- **Level 2: Job choice.** Agent picks what the pawn does next from a menu of legal jobs when the pawn is idle or at a decision point. Vanilla ThinkTree still handles emergencies, needs, and pathing. (RimMind Advisor.)
- **Level 3: Full pawn autonomy.** Agent overrides the ThinkTree; every job comes from the model. Expensive, slow, and fights the game.
- **Level 4: Colony command.** Agent has the player's tools. Orthogonal to pawn-level control.

Most existing work sits at A/B with Level 0, or C with Level 4. The interesting, mostly unoccupied space is **D with Level 2**: pawns with minds of their own, expressed through job choices and social behaviour, while the game engine keeps doing the boring parts.

---

## Option 1: "Pawns with inner lives" (D, Level 0–2)

Each colonist gets an agent with a persona built from traits, backstory, skills, ideology. The agent receives a stream of events the pawn would plausibly notice (nearby conversations, mood changes, injuries, deaths, raids, new arrivals). It maintains a Generative-Agents memory stream and periodically reflects. Its outputs are:

- Speech bubbles and a private journal (Level 0).
- Opinion and relationship nudges (Level 1).
- When the pawn goes idle or reaches a decision point, a choice from a menu of legal jobs (Level 2): "go talk to X", "work on Y", "pray", "wander to the graves".

**Watchability:** a side dashboard shows each pawn's current thought, last reflection, and goals. In-game bubbles show a one-line summary. A timeline lets you scrub.

**Why it fits RimWorld:** the game already simulates needs, health, mood, and pathing. We only need the model where the game is shallow: motivation, memory, narrative continuity.

**Risks:** cost scales with colony size. Pawns need to be "important enough" to earn a model call. Vanilla ThinkTree will still yank pawns into emergencies, which is correct but must be reported back to the agent as an observation.

## Option 2: "AI colony, human spectator" (C, Level 4)

One agent plays the whole colony via a REST/MCP bridge (RIMAPI or RimBridgeServer already exist). Human sits back and watches a stream. This is the Claude Plays Pokémon shape.

**Watchability:** reasoning summary panel, action log, colony vitals. Easy to stream on Twitch with an OBS overlay.

**Pros:** cheapest path to something running this week because the infrastructure exists. Single agent means simple cost model.

**Cons:** less novel. rimworld-ai-manager and RimMolt already do it. The interesting engineering is in the reflex layer (rule-based daemon for food, power, medicine) so the model is only woken for real decisions.

## Option 3: "Council of pawns" (E, Level 2 + a group decision layer)

Option 1 plus a shared social layer. Pawns can talk to each other through actual model-to-model dialogue, and colony-level decisions (accept the refugee, attack the raiders, banish the troublemaker) are put to the pawns as a debate whose outcome becomes a player-level action. Ideology precepts and roles give natural structure for this.

**Watchability:** the council debates are the show. An OBS scene switch to a "council" view when a big decision is pending.

**Risks:** coherence at scale; PIANO's bottleneck idea is the relevant prior art. Cost multiplies. Needs a hard cap on participants per debate.

## Option 4: "AI Narrator + AI Storyteller" (A + B, Level 0 and world-level)

No pawn agency at all. One agent narrates as a novelist; a second agent selects incidents to serve the narrative it is building. Ludeon's storyteller framework is designed for this and the DLCs add plenty of incident variety.

**Watchability:** text and voice. TTS makes it a podcast you play RimWorld alongside.

**Pros:** cheap, robust, no threading nightmares beyond the storyteller comp. Existing MIT-licensed code to borrow.

**Cons:** the agents are not "living in" the world. Probably a stepping stone, not the goal.

## Option 5: "Visitor agents" (D, Level 3 but for a handful of pawns)

Instead of colonists, the AI agents are traders, visitors, refugees, or a rival faction. They arrive with their own goals, negotiate, and leave. Because they are few and temporary, full autonomy (Level 3) is affordable, and the human still plays the colony. A visitor might try to steal, recruit a colonist, or propose an alliance.

**Watchability:** the human is playing, so the AI is an opponent or guest rather than something to spectate. Still worth showing the visitor's intentions in a panel.

**Pros:** contained scope, clear success criteria, and a genuinely new kind of gameplay.

---

## Watching: the spectator surface, regardless of option

- **In-game:** speech/thought bubbles (RimTalk's rendering approach), a new inspect tab on each pawn showing its agent state, letters when an agent does something notable.
- **Side dashboard:** a local web page fed by the orchestrator's WebSocket. Per-agent cards (persona, current goal, last thought, memory count, cost so far), an event ticker, and a timeline scrubber tied to game tick.
- **Stream overlay:** same page as an OBS browser source. obs-websocket to switch scenes on big events. Optional Twitch chat as a "whisper to a pawn" channel.
- **Replay:** every prompt, response, and action logged with the game tick and save. Replay a colony's day from the agents' point of view.
- **Tracing:** Langfuse for cost and latency per decision.

## Technical shape (common to options 1, 3, 5)

1. **RimWorld mod (C#, Harmony, net472).** Observes: Harmony postfixes on job start/end, interaction log, mood/thought changes, incidents, letters. Snapshots state to DTOs on the main thread. Acts: applies queued actions on the main thread each `GameComponentUpdate` (`TryTakeOrderedJob`, opinion tweaks, forced interactions). Talks: WebSocket client on a background thread, protocol modeled on the Neuro SDK (register actions with JSON schemas, context messages with a `silent` flag, action/result handshake with timeout).
2. **Orchestrator (Python).** One agent object per tracked pawn. Memory stream, salience gate, reflection scheduler, model tiering, cost budgets. Publishes the spectator event stream.
3. **Model tiers.** Local small model or Haiku for salience scoring and bubble text. Sonnet for routine decisions and dialogue. Opus for reflections and council-level decisions. Shared, cached prefix of world rules and persona.
4. **Time handling.** Game keeps ticking. Agent decisions land on a later tick. Reflex behaviour comes from vanilla. Optionally auto-pause at "council" moments. Disable agents at 3x/4x speed like RimTalk does.

## Build-vs-borrow

| Need | Borrow | Notes |
|---|---|---|
| Game state REST/SSE | RIMAPI (GPLv3) | License forces GPL on anything linked; fine for a hobby project, worth noting. |
| MCP observe/control | RimBridgeServer (MIT) | Aimed at mod testing but the observe/control tools are exactly what an overseer agent needs. |
| Dialogue bubbles + memory UI | RimTalk (CC BY-NC-SA) | Non-commercial, share-alike. Good to study, cautious to copy. |
| Provider gateway in C# | RimAI Framework (MIT) | Streaming, batching, cache. |
| Action-protocol design | Neuro SDK spec (MIT) | Copy the protocol shape. |
| Agent cognition | Generative Agents (Apache 2.0), AI Town (MIT) | Memory/reflection/planning reference implementations. |
| Multi-agent colony harness | RLE (MIT) | Pause-step-unpause loop, scoring, pluggable harness. |

## Open questions to settle before picking

1. Do we want to *play alongside* the agents, or *watch* them run a colony with no human input?
2. Is the goal believable characters (Option 1/3), a competent AI player (Option 2), or emergent society (Option 3)?
3. Budget: local models only, cloud only, or hybrid? This decides how many pawns can have minds.
4. Is streaming to an audience a goal, or just a nice side effect?
5. Which DLCs are in play? Ideology in particular gives roles and rituals that make a society layer much richer.

## Suggested first milestone

Regardless of the final answer, the cheapest useful first step is **an observation-only mod plus dashboard**: Harmony hooks that stream job changes, interactions, and mood events over WebSocket to a Python process that logs them and renders a live per-pawn page. No model calls yet. Every option above needs this layer, and it lets us see what the game actually exposes before designing agent prompts.
