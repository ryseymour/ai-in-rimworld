# Project Direction

Decided 2026-09-07 after reviewing `brainstorm-options.md`. This page is the current statement of what the project is. Update it when direction changes; keep the brainstorm as history.

## Decisions

1. **Pawns have inner lives and act autonomously.** Every tracked colonist is its own agent with persona, memory, and goals (brainstorm Option 1). The agent is not just a voice: it chooses what the pawn does within the game's legal actions. The game engine still owns needs, health, pathing, and emergency reactions.
2. **Agents talk to each other, and we watch the text.** Pawn-to-pawn conversations are real model-to-model dialogue, displayed as readable text (brainstorm Option 3, the council layer). Colony-level questions can be put to the pawns as discussions.
3. **Visitor agents are also autonomous.** Traders, refugees, raid leaders, and faction envoys arrive with their own goals and pursue them (brainstorm Option 5). They can negotiate, deceive, recruit, or leave.
4. **The user has a player character in the world.** One pawn is driven by the user directly. The user can walk it around and talk to any agent in natural language. The agents treat the player as just another inhabitant with a reputation and history. This replaces the top-down "god player" as the user's main way of interacting.

## What this implies

- **Two kinds of pawns:** agent-driven (colonists, visitors) and user-driven (the player character). Everything else stays vanilla.
- **Conversation is the core mechanic.** The dialogue system must handle agent↔agent, agent↔player, and group discussions with the same machinery.
- **Spectating is built in, not bolted on.** The dialogue transcript, per-pawn thoughts, and a timeline are first-class UI, both in-game and on a side dashboard.
- **Colony management is shared.** Since the user is playing as a pawn rather than as the overseer, colony-level decisions either emerge from agent discussion or the user influences them in character. Whether the user also keeps some top-down controls is an open question.

## Open questions

- Does the user keep any overseer powers (work tab, zones, drafting), or is it pure first-person? A hybrid where the player character can "propose" things to the group is probably the interesting version.
- How does the player character get chosen or created?
- How much can visitors do that vanilla visitors can't (theft, sabotage, persuasion)?
- Budget: how many pawns can have minds at once, and which model tier for which decision?
- Which DLCs are assumed? Ideology roles and rituals are a natural fit for the group-discussion layer.

## Related pages

- `brainstorm-options.md` for the alternatives considered.
- `../resources/` for the research behind this.
