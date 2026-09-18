# Design: inter-colony trade, traders, and procedural roads

Drafted 2026-09-18 from Ryan's ask: "we have a storage building, could we feature a way to have
traders from other colonies trade goods between them. procedural roads and pathways between villages."

This is a design, not an implementation. See "Status" for why.

## Status

This targets the **ascii colony sim** (`~/ascii-colony` on Ryan's Mac), which already runs several
colonies side by side and has the storage building. As of 2026-09-18 the RimWorld mod in this
repository is paused and the colony sim is the project.

The sim has no GitHub remote yet, so a cloud thread cannot read or change it. This page is written so
the work can start the moment `~/ascii-colony` is pushed and added to the project. Until then, treat
the structure below as proposed against a tile-based world holding several settlements, each with a
storage building and a population that produces and consumes goods — the specific names and modules
will need one pass against the real code.

## The shape of the feature

Three systems that are useful separately and much better together:

1. **A world graph with procedural roads.** Settlements are nodes; roads are carved paths between them
   that make travel cheaper and are visible on the map.
2. **Storage as the trade interface.** Each settlement's storage building is the single source of truth
   for what it has, what it can spare, and what it will pay. Trade reads and writes only storage.
3. **Traders as travelling agents.** A trader belongs to a home settlement, loads cargo out of its
   storage, walks the roads to a neighbour, exchanges goods, and walks home.

The reason to build them in that order is that each one is testable on its own: roads without traders,
then prices without movement, then movement.

## 1. Procedural roads

### Which settlements connect

Do not connect everything to everything; the map turns into a spiderweb and every route looks alike.

1. Build a candidate edge set from settlement positions — a Delaunay triangulation, or k-nearest
   neighbours plus the relative neighbourhood graph if that is less code. Both give plausible local
   connections and no long crossing edges.
2. Take a minimum spanning tree over those candidates, weighted by terrain-aware cost (below). The MST
   is what guarantees every village is reachable, which matters more than realism.
3. Add back a fraction of the rejected candidate edges — pick the ones whose detour ratio through the
   tree is worst, so you add the shortcuts a real traveller would have worn in. Roughly 15–25% of the
   remainder gives loops and alternate routes without the web.

### Carving the path

Each retained edge becomes actual road tiles, via A* across the terrain grid with a cost function that:

- penalises elevation change much more than distance (roads follow valleys and contours, and this one
  term is most of what makes generated roads look deliberate rather than drawn with a ruler),
- penalises water, swamp and dense forest, and prefers existing fords or narrow crossings,
- **discounts tiles that already carry a road.** This is the important one: it makes parallel routes
  merge into shared trunk roads instead of running side by side. Carve edges in descending order of
  expected traffic so the trunks form first and later routes bend to join them.

### Tiers and wear

A road tile has a tier — foot path, dirt road, paved — giving a movement multiplier (say 1.3×, 1.6×,
2.0×). Traffic accumulates on a tile and promotes it past a threshold; disuse decays it back. Trade
routes that actually get used become visibly better roads, and abandoned ones grass over. That is
cheap to implement and it is the thing that makes the system read as alive on the map.

### Determinism

Every step seeds from the world seed. Regenerating a world from a save must produce the same roads, or
saves break and nothing is reproducible in tests.

## 2. Storage as the trade interface

Per settlement, per good, two derived numbers:

- **reserve** — what the colony keeps for itself: consumption rate × a buffer in days (longer for food,
  shorter for luxuries).
- **surplus** — `stock − reserve`, floored at zero. Only surplus is offered for sale; only a negative
  gap is bought.

That single rule is what makes trade emerge from what colonies actually produce and consume, with no
scripted economy behind it. A colony with a good farm sells food; one on poor soil buys it.

**Price.** Local price per good is `base_price × f(stock / reserve)`, with `f` falling as stock rises —
a clamped curve, not a straight line, so a glut does not drive prices to zero. Scarcity is expensive,
glut is cheap, and a trader profits on the spread between two settlements. Prices therefore converge as
goods move, which makes the economy self-regulating instead of needing tuning per good.

**Transactions.** A trade is a two-sided transfer against both storages. Cargo is reserved out of the
seller's storage at load time so it cannot be eaten while in transit, and the buyer's side is only
checked on arrival — a colony's needs can change over several days of travel, so a trader must handle
arriving to find the deal worse than when it left (sell less, sell cheaper, or carry on to the next
village). Deliberately not an atomic transaction: the failure case is the interesting gameplay.

## 3. Traders

A trader is a pawn-like entity with a home settlement, a cargo manifest, a route, and a purse.

Its cycle:

1. **Dispatch.** A settlement considers sending a trader when it has meaningful surplus and knows a
   neighbour that wants it. Rate-limited so villages do not spam caravans.
2. **Load.** Take from surplus only, up to a carry capacity.
3. **Choose a destination.** Expected profit = value of the price gap at the destination, minus travel
   cost along the road graph, minus risk. Traders know neighbours' prices imperfectly — from the last
   visit, not live. Stale knowledge is what produces wasted trips and bad guesses, which is good.
4. **Travel** the road graph. Edge costs are precomputed at generation time, so world travel is a graph
   walk, not per-tile pathfinding; only movement inside a settlement needs the local pathfinder.
5. **Trade** against the destination's storage, at its prices.
6. **Return** and deposit goods and profit into home storage.

**Agent-driven traders.** This slots straight into project direction #3 (autonomous visitor agents).
The sim owns movement, inventory arithmetic and what is legal; the agent owns the handful of discrete
choices — go or not, where, what to carry, accept this offer or push back, and what to say. That is one
model call per leg rather than per tick, so it is affordable, and it gives negotiation dialogue, traders
who favour colonies they like, and traders who lie about what a good is worth back home. Build the
scripted version first and swap the decision points for agent calls; the interfaces are the same.

## Milestones

1. World graph and carved roads, rendered, deterministic. No traders.
2. Reserve, surplus and prices on storage, with no movement. A headless multi-colony run verifies the
   economy math alone.
3. Scripted traders walking the roads and exchanging goods.
4. Agent-driven traders with negotiation dialogue.
5. Risk and texture: bandits on the roads, weather closing routes, reputation between colonies, road
   wear and upgrade.

## How we know it works

A headless multi-day run across several colonies, asserting:

- every settlement is reachable from every other one on the road graph;
- **conservation** — total goods in the world change only by production and consumption, never by trade.
  A rounding bug in the exchange that mints or eats goods is the single most likely defect here;
- price variance for a given good across colonies falls over the run — proof that trade is doing its job;
- no caravan is stuck: every dispatched trader either arrives, returns, or dies for a stated reason.

## Open questions

- How many settlements, and are the non-player ones simulated at full fidelity or abstracted to
  production and consumption rates? Abstracting them is much cheaper and probably invisible.
- Does the player's colony trade through exactly the same code path? It should — one economy, no
  special case.
- Is a caravan simulated while travelling, or resolved on arrival? Simulated is needed for road ambush
  to mean anything.
- Do traders carry currency, or is it pure barter? Barter is more characterful and harder to balance.

## Related pages

- `project-direction.md` — decision 3, autonomous visitor agents, which the agent-driven trader extends.
- `brainstorm-options.md` — Option 5, visitor agents.
