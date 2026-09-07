# LLM / AI Agents in RimWorld and Similar Colony Sims — Survey

Research date: 2026-09-07. Steam Workshop pages were blocked by the sandbox proxy, so Workshop-only mods are described from search snippets and GitHub mirrors. Everything with a GitHub repo was read directly.

---

## 1. RimWorld mods: pawn dialogue / "chat with pawns"

### RimTalk (juicy / jlibrary)
- **What:** The dominant pawn-dialogue mod. Generates context-aware speech bubbles for pawns from mood, traits, relationships, current job, danger state, conversation history. Ecosystem of add-ons: Expand Memory (memory + timeline UI), Expand Actions (dialogue triggers real actions: recruit, romance, dine), TTS Addon / TTS Local, MemoryDigest, Lucid Chronicle, RimTalk-Quests, RimTalk Event+.
- **Hook:** C# mod; custom Defs (ThoughtDef, InteractionDef, JobDef, HediffDef) plus Harmony. Exposes a public API for other mods.
- **LLM:** Gemini, OpenAI, DeepSeek, Grok, GLM, OpenRouter, Qwen, Player2, custom base URL, Ollama / LM Studio.
- **Architecture:** Entirely in-game C#; prompts built with Scriban templates that can reference game objects; HTTP to provider from background thread.
- **Latency/cost:** Configurable "Talk Interval" (default 1 line / 4 s, 2 s in danger); "disable AI at high game speed"; simple vs. advanced (multi-key) config modes.
- **License:** CC BY-NC-SA 4.0.
- **URLs:** https://github.com/jlibrary/RimTalk , Workshop 3551203752, presets: https://github.com/r33Cy/RimTalk-Community-Preset-Collection , quests: https://github.com/Laurence-042/RimTalk---Quests

### RimDialogue (johndroper / Procedural Products)
- **What:** Fork of Jaxe's Interaction Bubbles; rewrites vanilla interaction log lines into real dialogue. ~100 context data points. "Additional Instructions" lets you set colony culture.
- **Hook:** Harmony 2.3.3, four patches: postfix `PlayLog.Add`, postfixes on `PlaySettings` / `MapInterface` GUI, prefix `MemoryUtility.ClearAllMapsAndWorld`.
- **Architecture:** Client/server. Client mod POSTs to a server over HTTP. "RimDialogue Free" uses the author's hosted server; "RimDialogue Local Server" is a .NET 9 app at `http://localhost:7293/`.
- **LLM:** Local server supports Ollama, Groq, AWS, OpenAI.
- **Latency/cost:** Server-side `RateLimit` in requests/sec (0.5–1.0 for Ollama, lower for cloud).
- **License:** Server CC BY-NC-SA 4.0; client not stated.
- **URLs:** https://github.com/johndroper/RimDialogueClient , https://github.com/johndroper/RimDialogueServer , https://rimdialogue.proceduralproducts.com/

### RimChat / RimChat – Word to Actions
- **What:** Pawn dialogue + TTS with per-pawn voices; LLM-driven comms-console diplomacy; AI-triggered actions (mood change, romance, proposals, recruiting). Reads RimTalk memories. RimMind has a "Bridge (RimChat)" module.
- **Hook/arch:** In-game C#; intercepts interactions. Provider-selectable LLM + TTS. Requires internet.
- **URLs:** Workshop 3623376155 (RimChat), 3683001105 (Word to Actions). No GitHub source found.

### Social Interactions (AI-powered) / Local AI Social Interactions (gavinblair)
- **What:** LLM dialogue + TTS with memory; providers include KoboldCpp, Ollama, LM Studio, OpenAI, Gemini, Claude. Earlier local-only version needs Ollama `llama3.2:3b`.
- **URLs:** Workshop 3589636018; https://github.com/gavinblair/SocialInteractions ; Workshop 3413305419

### FelPawns
- **What:** "AI NPC engine": talk to pawns and pawns talk to each other with spatial awareness and colony knowledge. Windows-only (embeds ONNX runtime for local embeddings).
- **URLs:** Workshop 3650090096; https://blog.walterfreedom.com/ . No public source.

### OpenRimWorldAI / AskAPawn (LuckyKo)
- **What:** Base library exposing `SendPromptAsync()` for other mods, daily pawn "reports"; AskAPawn lets you question a pawn. Tested with Gemini Flash via OpenRouter.
- **URLs:** Workshop 3411917876, 3412825218; https://github.com/LuckyKo/rimworldmods

---

## 2. RimWorld mods: narrator / storyteller / commentary

### RimGPT (Brrainz / pardeike)
- **What:** The original (2023) LLM mod. Spoken AI commentary on gameplay with personas; raid flavor.
- **Hook:** Harmony patches on game events; in-game C#.
- **LLM/TTS:** OpenAI + Azure neural TTS; author says local models make it worse. ~$2 per ~1M words.
- **License:** MIT. Supports 1.4–1.6.
- **URLs:** https://github.com/pardeike/RimGPT , Workshop 2960127000

### Tales from the RimWorld ("The Narrator")
- **What:** Custom storyteller that narrates why incidents happen (2–4 sentences grounded in colony state).
- **Hook:** `StorytellerComp_LLM` extends vanilla storyteller intervals and queues a narration request before yielding the incident.
- **LLM:** OpenRouter via async `UnityWebRequest`. ~650–850 tokens per call.
- **Latency/cost:** 10 s timeout then vanilla fallback; cap ~50 calls per in-game day.
- **License:** MIT. **URL:** https://github.com/adhikasp/TalesFromTheRimWorld

### Claude Storyteller (S4L7)
- **What:** Reads wealth, defenses, mood, food, history and chooses events on three cycles (minor, major, narrative arc).
- **LLM:** Anthropic API. $0.01–0.05/hour.
- **URLs:** https://github.com/S4L7/ClaudeStoryteller , Workshop 3660893527

### RimAI (storyteller) and Rimteller
- RimAI: event-generating storyteller; many providers incl. Pollinations (free). Workshop 3652573198.
- Rimteller "Residuals": uses colony trends and history. Workshop 3638662307.

---

## 3. RimWorld: LLM *controls* the colony (agentic)

### RIMAPI (IlyaChichkov) — key enabling infrastructure
- **What:** REST API server inside RimWorld at `http://localhost:8765/`, 120+ endpoints (colonists, health, mood, skills, work priorities, resources, research, orders, save loading, difficulty) plus SSE event stream. Caching, non-blocking.
- **License:** GPLv3. RimWorld 1.5–1.6.
- **URLs:** https://github.com/IlyaChichkov/RIMAPI , https://ilyachichkov.github.io/RIMAPI/ , Workshop 3593423732
- Similar: ARROM (Workshop 3525153789).

### rimworld-ai-manager (agulaya24)
- **What:** Claude plays RimWorld via RIMAPI. Two layers: Python "homeostasis daemon" polling REST with rule-based reflexes (no LLM); Claude is the strategy layer, woken only for escalations. Motivation: "model latency is slow against the game clock". Postmortem loop turns failures into new daemon rules.
- **License:** MIT. **URL:** https://github.com/agulaya24/rimworld-ai-manager

### RLE — RimWorld Learning Environment (AppSprout-dev)
- **What:** Multi-agent benchmark: 7 role agents (MapAnalyst, ResourceManager, DefenseCommander, ResearchDirector, SocialOverseer, ConstructionPlanner, MedicalOfficer) in a hub-spoke network.
- **Architecture:** Python; loop = pause → read state (RIMAPI REST + SSE) → harness.step → execute → score → unpause. Pluggable harness (incl. MCP coding agents).
- **Cost:** $0.12–$7.00 per scenario.
- **License:** MIT. **URL:** https://github.com/AppSprout-dev/RLE

### RimMolt and RimBridgeServer (MCP)
- **RimMolt:** In-process MCP server (`http://localhost:8787/mcp`); connect Claude Code / Codex / Claude Desktop and the agent runs the colony. Workshop 3796006886. No source located.
- **RimBridgeServer (pardeike):** MCP server inside RimWorld for observe/control: UI/camera/selection, designators, debug actions, time speed, screenshots, JSON/Lua scripting, profiler; token-authenticated; extensible via `BridgeTools` DLLs. Aimed at AI-driven mod testing. MIT. https://github.com/pardeike/RimBridgeServer
- Others: https://github.com/She11code/Mcp-of-RimWorld , RimWorldMCP (codexvn).

### RimMind suite
- **What:** Modular C#: Core (API client, async queue, retry, JSON-forced responses), Memory, Dialogue, Actions (intents like `assign_work` → game ops), Advisor (idle/low-mood pawn: LLM role-plays and picks a character-consistent action), Bridge.
- **License:** MIT. **URL:** https://github.com/RimWorld-RimMind-Mod/

### RimAI Framework + Core (oidahdsah0)
- **What:** Provider-agnostic C# LLM/embeddings gateway (JSON provider templates), streaming, batching, cache. Core adds DI, scheduler, circuit breakers, personas, tooling.
- **License:** MIT.
- **URLs:** https://github.com/oidahdsah0/Rimworld_AI_Framework , https://github.com/oidahdsah0/Rimworld_AI_Core

### Curated list: "Mods that incorporate AI" (Workshop 3463214912)

---

## 4. RimWorld multiplayer (spectating / shared-world infra)

- **RimWorld Together:** server-authoritative shared planet; standalone .NET server / Docker. https://github.com/RimWorld-Together/Rimworld-Together
- **Zetrith's Multiplayer (rwmt):** lockstep deterministic sync of one shared colony. https://github.com/rwmt/Multiplayer
- **OpenWorld (D12-Dev):** https://github.com/D12-Dev/OpenWorld

---

## 5. Generative-agent research and hobby projects (non-RimWorld)

| Project | What | Game hook | LLM | Architecture | Latency / cost | License | URL |
|---|---|---|---|---|---|---|---|
| **Generative Agents / Smallville** (Stanford 2023) | 25 agents with memory stream, reflection, planning | Custom Phaser/Django world | GPT-3.5/4 | Python backend + Django frontend; lockstep steps | "Thousands of dollars" for 2 sim-days | Apache 2.0 | https://github.com/joonspk-research/generative_agents , https://arxiv.org/abs/2304.03442 |
| **AI Town** (a16z) | Deployable Smallville clone | Own engine on Convex | OpenAI (forks add Ollama) | 1 step/s loop; async LLM ops re-enter as inputs; vector memory | ~1.5 s input latency | MIT | https://github.com/a16z-infra/ai-town |
| **Voyager** (NVIDIA) | Lifelong-learning Minecraft agent; skill library of code | Mineflayer via Python | GPT-4 | External Python + Node | Agent paces game | MIT | https://github.com/MineDojo/Voyager |
| **Mindcraft** | Multi-agent Minecraft bots with dialogue and RAG | Mineflayer | 16+ providers | External Node server | User-configured | MIT | https://github.com/mindcraft-bots/mindcraft |
| **Project Sid** (Altera) | 10–1000+ agents forming roles, religion, taxes | Minecraft | Undisclosed | PIANO: parallel modules + coherence bottleneck | Undisclosed | Paper only | https://arxiv.org/abs/2411.00114 |
| **dwarf-ai** (dknos) | Per-dwarf agents with episodic memory (ChromaDB), Legends RAG, structured in-engine actions | DFHack Lua bridge | Gemini Flash Lite default | Python sidecar | 30 turns < $0.001 | see repo | https://github.com/dknos/dwarf-ai |
| **df-ai** | Scripted (non-LLM) DF autoplayer | DFHack | none | Ruby/C++ | — | — | https://github.com/BenLubar/df-ai |
| **LLM Agent for Dwarf Fortress** blog (trine, 2026) | Blog series | — | — | — | — | — | https://blog.trine.dev/posts/2026-02-28-df-ai-exp/ |
| **1001 Nights** | AI-native narrative game | Unity | GPT-4 + SD | Cloud calls | n/a | Commercial | https://www.1001nights.ai/ |

---

## 6. Spectating / streaming setups

| Setup | How it works | Relevance |
|---|---|---|
| **Twitch Plays Pokémon** | IRC bot parses chat commands into emulator keypresses; overlay tallies votes | Crowd input template: https://github.com/hzoo/TwitchPlaysX , https://github.com/molleindustria/TwitchPlaysEverything |
| **Claude Plays Pokémon / Gemini Plays Pokémon** | Emulator + harness: screenshot + RAM state fed to model with tools; model-maintained notes; periodic summarization; overlay shows reasoning | Best public example of an LLM-run 24/7 stream with visible reasoning. https://www.twitch.tv/claudeplayspokemon , https://blog.jcz.dev/the-making-of-gemini-plays-pokemon , https://www.latent.space/p/how-claude-plays-pokemon-was-made |
| **Neuro-sama** (Vedal) | Python LLM + RAG; **Neuro Game SDK**: game opens WebSocket, registers typed actions (name, description, JSON schema), receives `action`, replies `action/result`; ~20 s timeout; "Randy" random bot for testing; Unity/Godot SDKs | Clean proven protocol for letting an LLM play a game via typed actions; portable to a RimWorld mod. https://github.com/VedalAI/neuro-sdk |
| **RimMolt / RimBridgeServer** | MCP-in-process lets an agent run the colony while you watch | Closest thing to "AI plays RimWorld, you spectate" today |

---

## 7. Cross-cutting patterns

1. **Two integration styles in RimWorld:**
   - *In-game C# (Harmony + HttpClient/UnityWebRequest on a background thread)*: RimTalk, RimGPT, RimMind, RimAI, Tales, Claude Storyteller. Simplest for Workshop distribution; must never block the tick.
   - *Bridge mod + external process*: RIMAPI (REST+SSE) → Python (rimworld-ai-manager, RLE); MCP servers (RimMolt, RimBridgeServer) → Claude Code/Codex; RimDialogue's .NET server. Preferred for agents that *control* the game.
2. **Latency handling:** fixed cadence/throttle (RimTalk 4 s, Tales 50/day), timeouts with vanilla fallback, pause-step-unpause loops (RLE), or reflex-vs-strategy layering so the LLM is off the critical path (rimworld-ai-manager, AI Town).
3. **Cost:** dialogue mods rely on cheap/free tiers. Storyteller mods at ~700 tokens/call cost cents per hour. Full agentic control (RLE) is $0.12–$7 per scenario; Smallville-scale simulation cost thousands.
4. **Memory:** most dialogue mods bolt on a memory module (RimTalk Expand Memory, RimMind-Memory, FelPawns ONNX embeddings, dwarf-ai ChromaDB, AI Town vectors).
5. **Licenses:** RimTalk/RimDialogue CC BY-NC-SA; RimGPT, RimMind, RimAI, Tales, RLE, rimworld-ai-manager, RimBridgeServer, Voyager, Mindcraft, AI Town MIT; RIMAPI GPLv3; Generative Agents Apache 2.0.
