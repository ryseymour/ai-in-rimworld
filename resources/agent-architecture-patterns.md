# Architecture Patterns for Live-Watchable LLM Agents in a Real-Time Sim

Research date: 2026-09-07. Some primary sources (arxiv, anthropic.com, steamcommunity) were blocked by the sandbox proxy; for those the URL is cited and content relies on search summaries plus well-known paper content. The original research agent referenced CK3 in places because of its working directory; those notes are dropped here except where the pattern (file/log bridges) is still useful.

---

## 1. Game-to-LLM bridges

### 1a. In-process calls from a C#/Unity mod

**Pattern:** the mod owns an `HttpClient`/`UnityWebRequest`, fires the request off the main thread, and marshals the result back onto the main thread before touching game state.

- **Main-thread constraint.** Unity only allows engine API calls from the main thread. `async/await` with `HttpClient` runs I/O on the threadpool but you must dispatch the continuation back. Tools: [UnityMainThreadDispatcher](https://github.com/U3DC/UnityMainThreadDispatcher), [gilzoide/unity-main-thread-task](https://github.com/gilzoide/unity-main-thread-task), [UniTask](https://github.com/Cysharp/UniTask). Comparison: [Unity async vs coroutines](https://www.educative.io/answers/unity-async-vs-coroutines).
- **Anti-pattern:** a UnityMCP design doc describes an HTTP proxy that processed requests synchronously on the main thread during `PollEvents()`, blocking the game; the fix was a background-thread server dispatching only Unity calls to main ([UnityMCP async proxy design](https://glama.ai/mcp/servers/@Bluepuff71/UnityMCP/blob/dfed172af5ffe530547a69d03a0dee00e07d82ef/docs/plans/2026-01-25-async-native-proxy-design.md)).
- **Worked RimWorld examples:** [RimAI Framework](https://github.com/oidahdsah0/Rimworld_AI_Framework) (layered facade → coordinator → HTTP; `await foreach` streaming; concurrency-limited batching; provider templates), RimTalk and Local AI Social Interactions (local Ollama/LM Studio/KoboldCpp plus cloud, hybrid fallback), [RimDialogueServer](https://github.com/johndroper/RimDialogueServer) (thin mod + separate server).
- **In-process local inference:** [LLMUnity](https://github.com/undreamai/LLMUnity) wraps llama.cpp inside the Unity process; multiple `LLMAgent`s share one `LLM`; "Remote" mode serves other clients. Trade-off: VRAM/CPU contention with the game.

**When it fits:** single shippable mod; LLM latency acceptable because actions queue and apply on a later tick.

### 1b. External orchestrator process (Python/Node)

**Pattern:** the game exposes state and accepts commands; a separate process runs cognition and pushes actions back. Dominant in every "agents live in a world" project: decouples LLM latency from the tick, allows Python tooling, and the orchestrator doubles as the spectator data source.

| Transport | Example | Notes |
|---|---|---|
| **WebSocket, typed action protocol** | [Neuro SDK](https://github.com/VedalAI/neuro-sdk) ([spec](https://github.com/VedalAI/neuro-sdk/blob/main/API/SPECIFICATION.md)) | Game sends `startup`, `context` (with `silent` flag), `actions/register` (name, description, JSON schema), `actions/unregister`, `actions/force`; AI sends `action`; game replies `action/result` within ~20 s or the action is abandoned. Official Unity/Godot SDKs. README stresses race conditions. Cleanest published blueprint for a game↔agent contract. |
| **Bot library over game protocol** | [Mindcraft](https://github.com/mindcraft-bots/mindcraft), [mc-agents](https://github.com/jblemee/mc-agents) | Mindcraft splits models into chat/code/vision/embedding roles per bot; mc-agents splits "reflexes" (no LLM) from "strategy" (Claude writes JS calling `tools.*`; persistent `MEMORY.md`). |
| **Serverless DB + engine in functions** | [AI Town ARCHITECTURE.md](https://github.com/a16z-infra/ai-town/blob/main/ARCHITECTURE.md), [AI Town v2](https://stack.convex.dev/ai-town-v2) | Engine 60 ticks/s batched to 1 step/s. Agents `startOperation` for LLM work, `inProgressOperation` limits to one op per agent, results submit into a monotonically numbered `inputs` table consumed next step. ~1.5 s input latency. |
| **IPC/gRPC with deterministic tick** | [AgentArena](https://github.com/JustInternetAI/AgentArena) | Godot deterministic tick loop; Python receives observation snapshots, returns JSON-schema tool calls; msgpack replay logs. |
| **HTTP/SSE plugin** | [GodotAgent](https://github.com/Wizzerrd/GodotAgent) | Game calls a local agent server; SSE for streaming tokens. |
| **Emulator memory + screenshots** | [llm_pokemon_scaffold](https://github.com/cicero225/llm_pokemon_scaffold), [GeminiPlaysPokemonLive](https://github.com/nichosta/GeminiPlaysPokemonLive) | Emulator keeps ticking while the LLM thinks; RAM reads become a textual overlay/minimap. |
| **File queues / log tailing (no mod API)** | [Voices of the Court](https://github.com/Demeter29/Voices_of_the_Court) (CK3), mc-agents `status.json`/`outbox.json` | Fallback pattern when the game can't do networking: watch a log, run the LLM, write command files the mod polls. Not needed for RimWorld but useful for prototyping. |

**Recurring latency/tick patterns:**
- **Never block the tick on inference.** Let the world advance; the action lands on a later tick as an input.
- **Inputs go through an ordered queue** so the engine stays deterministic and replayable.
- **Give the agent a "still thinking" default** (reflexes; Player2's per-tick queue that batches messages into one LLM call: [Building AI NPCs with Player2](https://blog.player2.game/p/building-ai-npcs-with-player2-api)).
- **Timeouts and abandonment:** Neuro drops an action after ~20 s; code-as-action needs sandboxing (Mindcraft README warns of injection).

---

## 2. Agent cognition designs

### 2a. Stanford Generative Agents (memory stream / reflection / planning)
- Paper: [arXiv 2304.03442](https://arxiv.org/abs/2304.03442); code: [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents).
- **Memory stream:** append-only natural-language observations, plans, reflections with timestamps. **Retrieval** scores recency (exponential decay, 0.995/hour), importance (LLM-rated 1–10 at write time), relevance (embedding cosine); top-k into the prompt.
- **Reflection:** triggered when summed importance of recent events crosses a threshold (~150); LLM generates 3 salient questions, retrieves, writes higher-level insights back with citations.
- **Planning:** hierarchical day plan in 5–8 chunks, decomposed to hour then 5–15 minute actions; re-plan when a perceived event warrants ("should the agent react?").
- Ablations showed observation, planning and reflection each needed for believability. Runtime: one step = 10 game-seconds; Django frontend renders/replays.
- Derivatives: [AI Town](https://github.com/a16z-infra/ai-town), [nmatter1/smallville](https://github.com/nmatter1/smallville).

### 2b. Voyager skill library
- [arXiv 2305.16291](https://arxiv.org/abs/2305.16291), [voyager.minedojo.org](https://voyager.minedojo.org/).
- (1) **automatic curriculum** (propose next task from state to maximize novelty); (2) **skill library** of executable programs indexed by embedding of description, retrieved for reuse/composition; (3) **iterative prompting** with environment feedback and self-verification until the task passes, then stored.
- For a sim: code-as-action gives temporally extended, reusable, interpretable behaviours and avoids catastrophic forgetting.

### 2c. ReAct-style tool loops
- [ReAct (Yao et al.)](https://arxiv.org/abs/2210.03629); [Arize explainer](https://arize.com/blog/keys-to-understanding-react/).
- Thought → Action (tool call) → Observation; with function-calling APIs this is `while stop_reason == "tool_use"`. In games the tools are queries (`look_around`, `get_relations`) and actions (`move_to`, `say`). The Neuro SDK's registered action schemas are exactly this tool list exported by the game.

### 2d. Many-agent architectures: PIANO (Project Sid)
- [arXiv 2411.00114](https://arxiv.org/abs/2411.00114). Many concurrent modules (memory, goal generation, social awareness, talking, skill execution) run at different clock rates and share state; a **cognitive controller** with an information **bottleneck** keeps speech and actions coherent. Scaled 10–1000+ agents in Minecraft; at 1000 the game server, not the LLM, became the limit.

### 2e. Cheap-vs-expensive model tiers
- Mindcraft per-role models; mc-agents: "Sonnet offers the best cost/efficiency ratio. Opus is the most capable but 30x more expensive."
- mc-agents System 1 / System 2 split (reflexes without any LLM; strategy with the big model) is the cheapest tier of all.
- Industry practice: "LOD-of-intelligence" tiering, small models for background NPCs, ~800 ms conversational budgets ([Cinevva guide](https://app.cinevva.com/guides/ai-npcs-dialogue), [Inworld latency guide](https://inworld.ai/resources/inference-latency-optimization), [LLMs and Games survey](https://arxiv.org/pdf/2402.18659)).
- With Claude: Haiku 4.5 for importance scoring, status lines, reaction gating; Sonnet 5 for routine planning and dialogue; Opus 5 for reflections and pivotal decisions. Newer models at low effort often beat older models at high effort, so one model with `output_config.effort` tuned per route is worth measuring before building a cascade (keeps one prompt-cache namespace).

### 2f. Event-driven triggering vs polling
- Generative Agents poll every step with cheap "should I react?" checks; AI Town idles agents until a timer or nearby event; Player2 batches queued messages per tick; RimTalk fires on social events/mood changes; Neuro's `context` has a `silent` flag and `actions/force` demands a decision now.
- Event-driven agents cut latency 70–90% and cost nothing idle ([Airbyte](https://airbyte.com/blog/comparing-architectures-for-agent-triggers), [dev.to patterns](https://dev.to/thedailyagent/event-driven-ai-agents-patterns-that-scale-39ld)). Recommended hybrid: game emits typed events → orchestrator scores salience cheaply (rules or Haiku) → only salient events wake the expensive planner; plus a slow heartbeat (per in-game day) for planning and reflection.

---

## 3. Observability and spectator UX

**What "AI plays game" streams show:**
- **Claude Plays Pokémon** ([Twitch](https://www.twitch.tv/claudeplayspokemon/about), [Anthropic visible thinking](https://www.anthropic.com/research/visible-extended-thinking)): three-panel layout, reasoning text scrolling left, game right, party/status strip bottom. Visible thinking is the show.
- **Gemini Plays Pokémon** ([making-of](https://blog.jcz.dev/the-making-of-gemini-plays-pokemon)): screenshot overlaid with RAM-derived labels, text minimap, running summary (summarize every 100 turns, recompress every 1000), secondary agent outputs. [GeminiPlaysPokemonLive](https://github.com/nichosta/GeminiPlaysPokemonLive) also pipes Twitch chat hints into the prompt.
- **Neuro-sama**: avatar + TTS rather than thoughts; games talk to her over the WebSocket action protocol.
- **Open-LLM-VTuber** ([GitHub](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)): explicit "display AI's inner thoughts" mode; frontend/backend split over WebSocket.

**In-world overlays / thought bubbles:**
- Smallville renders each agent's current action as an **emoji speech bubble** (cheap LLM call translates action string to emoji), with a dashboard listing memory streams, current activity, location, and every prompt sent.
- AI Town shows conversations in a side panel; click an agent to read identity, plan, recent messages.
- RimTalk/RimWorld mods draw dialogue as in-game bubbles; Mindcraft exposes a web UI on port 8080.

**Replay:** Generative Agents replay any saved sim from any step; AI Town keeps per-step history buffers; AgentArena logs msgpack replays. Equivalent here: log every prompt/response/action with in-game tick so a viewer can scrub the timeline.

**Log streams and tracing:** [Langfuse](https://langfuse.com/docs/observability/overview) (open source, self-hostable; hierarchical traces with every LLM call, tool call, cost, latency), AgentOps ([comparison](https://aimultiple.com/agentic-monitoring)). Emit one trace per agent decision tagged with agent id and game time.

**Twitch/OBS:**
- OBS **Browser Source** at a localhost page subscribed to the orchestrator's WebSocket is the standard way to render thoughts, agent cards and event tickers over the game capture ([OBS browser source](https://obsproject.com/forum/resources/stream-overlay-input-browser-source.962/), [websocket overlay example](https://github.com/airbenich/obsOverlay)).
- [obs-websocket 5.x](https://github.com/obsproject/obs-websocket) (port 4455) lets the orchestrator switch scenes programmatically, e.g. cut to a "council" scene during a big decision.
- Twitch chat as input: GeminiPlaysPokemonLive, [OpenTAAI](https://github.com/theubie/OpenTAAI).
- Show *summarized* reasoning, not raw chain of thought. Current Claude models return thinking as a summary (`thinking: {type: "adaptive", display: "summarized"}`); the default `display: "omitted"` just looks like a long pause on stream.

---

## 4. Cost and latency budgeting for many agents

**Local models:**
- Ollama: `OLLAMA_NUM_PARALLEL` sets concurrent requests per loaded model; `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_MAX_QUEUE`; context split across slots, weights loaded once ([parallel requests](https://www.glukhov.org/llm-performance/ollama/how-ollama-handles-parallel-requests/)). MLX runner on Mac serializes regardless ([issue #17666](https://github.com/ollama/ollama/issues/17666)).
- llama.cpp `llama-server`: `-np/--parallel` slots, continuous batching, `--cache-prompt` reuses KV cache across shared prefixes, slot save/restore, `/slots` and Prometheus metrics, OpenAI-compatible endpoints ([server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)). `-np` beyond ~4 gives little on one consumer GPU.
- Speculative decoding gives 2–3x on predictable dialogue. If game and model share one GPU, in-process inference competes with rendering; separate machine or LLMUnity Remote mode avoids that.

**Claude API levers** ([prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing)):
- **Prompt caching:** cache reads 0.1x input price (0.025x on Fable 5.1); 5-min writes 1.25x, 1-hour writes 2x. Min cacheable prefix is model-dependent (512 tokens Opus 5/Fable 5, 1,024 Sonnet 5, 4,096 Haiku 4.5); up to 4 breakpoints; order `tools → system → messages`. For a sim: world rules, tool definitions and static persona first under a 1-hour breakpoint; shared world-state digest next; per-decision observations last. Anything volatile after the last breakpoint. Verify with `usage.cache_read_input_tokens`. Pre-warm with `max_tokens: 0`. Changing effort/thinking/tool_choice invalidates the cache; caches are model-scoped (argument against multi-model cascades).
- **Message Batches API:** 50% off, usually under an hour, stacks with cache reads. Use for nightly reflections, importance re-scoring, backstory generation, replay narration.
- **Tiering and effort:** Haiku 4.5 $1/$5, Sonnet 5 $2/$10, Opus 5 $5/$25 per MTok; `output_config.effort` trades depth for tokens within one model and keeps the cache.
- **Budgeting method:** judge cost per completed agent-decision; measure with `response.usage`; set per-agent daily token budgets; `output_config.task_budget` (beta) caps an agentic loop.

**Architectural cost controls seen in the projects:**
- One in-flight LLM op per agent (AI Town) plus a global concurrency limiter (RimAI) to prevent stampedes when a world event touches everyone.
- Batch queued events into one call per agent (Player2).
- Summarize/compact context on a schedule.
- Do the boring stuff without a model (reflexes; rule-based salience filtering).
- Amortize world context: one shared, cached "state of the world" block reused across agents.

---

## 5. Recommended reference architecture (synthesis)

1. **Bridge:** external Python orchestrator with a typed action protocol modeled on the Neuro SDK. Thin RimWorld mod runs the WebSocket client on a background thread and dispatches to main thread.
2. **World loop:** engine ticks freely; agent actions enter an ordered input queue and apply next tick. One in-flight operation per agent.
3. **Cognition:** Generative-Agents memory stream with recency/importance/relevance retrieval and threshold-triggered reflection; ReAct tool loop for decisions; optional Voyager-style library of reusable scripted behaviours; reflex layer with no model.
4. **Triggering:** game events → cheap salience gate → planner wake-up; slow heartbeat for planning/reflection; batch API for nightly work.
5. **Spectator:** orchestrator publishes a WebSocket event stream (thought summary, chosen action, tool calls, cost); in-game bubbles; OBS browser-source overlay and side dashboard; Langfuse traces and a tick-indexed replay log; obs-websocket for scene switching; optional Twitch chat hints.
6. **Cost:** stable cached prefix (rules + persona + shared world digest), effort tuned per route, tiering by decision importance, local llama.cpp with `-np` slots and `--cache-prompt` for the chatter tier.
