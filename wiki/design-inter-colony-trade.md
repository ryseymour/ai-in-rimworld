# Design: inter-colony trade, traders, and procedural roads

Drafted 2026-09-18 from Ryan's ask: "we have a storage building, could we feature a way to have
traders from other colonies trade goods between them. procedural roads and pathways between villages."

## Status

This targets the **ascii colony sim** (`~/ascii-colony` on Ryan's Mac), which already runs several
colonies side by side and has the storage building. As of 2026-09-18 the RimWorld mod in this
repository is paused and the colony sim is the project.

That sim has no GitHub remote, so a cloud thread cannot read or change it. Milestones 1–4, the
wildlife and reputation parts of milestone 5 and population (milestone 6) are therefore **built
standalone in `sim/colonysim/`** in this repository: stdlib only, no dependencies, so it lifts into
the real sim as a module. `sim/README.md` describes what is there. The names below are the design's
names; where the code differs, the code is
what runs. Milestone 4 is built: stewards decide, and traders haggle in dialogue (section 3b).

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

## 3a. Stewards: who decides

Built 2026-09-19 from Ryan's ask: "give stewards access to the trade networks and be able to
adjust prices", and "make it a real economic simulation between the three colonies".

Everything above this section is mechanism. Land makes goods, scarcity makes prices, caravans move
things between the two, and nothing in any of it decides anything. A **steward** is the agent that
runs one colony's side of the economy. It is the object the ascii sim's own `colony/steward.py`
plugs into, and the seam milestone 4 needs.

**What a steward sees** (`NetworkView`, rebuilt fresh each day so it never holds the world):

- every colony it can reach, with today's travel days, today's hazard and how worn the road is;
- what the last caravan home reported about each market -- prices, what was spare, what was wanted
  -- with the day it was seen, so old news is visibly old news;
- its own caravans, and nobody else's. What other colonies are doing it learns the way a trader
  does, by going there.

**What a steward may change** (`Policy`, on the colony, clamped on the way in so an agent can ask
for anything without the rest of the sim having to defend itself):

- **markup**, 0.6x to 1.8x on what scarcity alone would ask. One price serves both sides of the
  counter -- it is what a visiting caravan is paid here and what this colony pays for imports --
  which is what makes it a decision rather than a readout;
- **reserve**, 0.4x to 2.5x the good's own buffer days, which moves the line between what the
  colony sells and what it wants to buy;
- **focus**, 0.5x to 1.6x on the land's own output, rebalanced so the colony's total output at base
  prices is unchanged. People move between jobs; they do not appear.

**The scripted steward** (`merchant`) is three rules:

- *short of something*: work backwards from the trader's own sum -- find the cheapest place known
  to have any, add the margin a trader wants and what the road is worth, and quote that. Scarcity
  already lifts the price on its own, so the bid only does anything when that is not enough. A
  colony with no coin does not bid, because it would be paying in barter off the shelves it is
  trying to fill;
- *sitting on a pile*: discount, and if another colony could supply the buyer it wants, discount to
  just under them. Two colonies with wood and one buyer for it is a competition;
- *over weeks*: hold more back of whatever it keeps running down, and move people toward what it
  keeps running out of and what the region is paying for.

That last rule is what makes this an economy rather than a delivery service: a price that stays
high long enough stops being a reason to buy and becomes a reason to make. Measured, it is the
difference between a colony that starves when the roads are cut and one that puts people in the
fields instead.

**Stewards are on by default**, and `build_simulation(stewards=False)` is the control case, the
same way `trade_enabled` is the control case for traders. Every claim about what stewards do is
made against it.

**Milestone 4 plugs in here.** `Steward(colony, decide=...)` replaces the scripted rules with
anything of the same shape -- a player, a model call once a week -- reading the same view and
writing through the same clamped setters. `Steward.brief()` renders the whole situation as text for
exactly that, and is deliberately the same facts the scripted merchant reasons over rather than a
summary of them. The other half of that milestone is section 3b: what a steward says when a cart is
actually at its counter.

## 3b. Haggling: how the price is actually agreed

Built 2026-09-19. Section 3a gave each colony an agent and something to decide. This is the other
half of milestone 4: the moment two of them meet.

Until now a sale was arithmetic. A caravan arrived, the host's shelves said what the goods were
worth, and that was the price -- neither party had a say in it. Now the visitor and the host argue
it out, one good at a time, and the price is what they agree on.

**Two numbers a side.** A *limit* it will not cross, and an *opening* nowhere near it.

- the host's limit is its own price plus whatever the road was worth, capped at what the good can
  fetch there -- which is exactly what the sim used to charge outright. The old take-it-or-leave-it
  price is now the *most* a host can be talked into, and everything below it the trader got by
  arguing;
- the trader's limit is what the cargo was worth at home when it was loaded, recorded on the
  caravan at dispatch. Below that it is better off carting the goods back.

**Turns.** Each turn a side takes what is on the table or names a price a little closer to the
other's. How fast it gives that ground away is the only thing that differs between two negotiators,
and it is the whole texture of the feature: a host four days from an empty granary concedes early
and pays for it, one merely topping up holds out and pays less -- and buys less of it, since a
price a colony dislikes does not stop it buying, it makes it buy less. By its last turn every
negotiator is standing on its own limit, so the exchange always ends.

**A deal is struck exactly when the limits overlap**, and never outside them. When they do not, the
goods stay on the cart and go home: a trip that did not pay, which the sim had no way to express
before. It is rare on purpose -- a caravan only sets out when the sums looked good -- and measured
at about one journey in two hundred.

**The dialogue is recorded**, not just the outcome, because the argument is the part a reader
learns anything from. The last thirty are on `Simulation.negotiations`, the last few on each
`Steward`, and the browser viewer shows them under *At the counter*. Nothing is random: a seed
replays the same argument word for word.

**Where the model goes.** `bargain` is the scripted negotiator; `Steward.negotiator` replaces it,
the same seam as `decide` one level down -- `decide` is the stance a colony takes over weeks,
`negotiator` is how it argues a single sale. Whatever is talking gets `Haggle.brief(side)` and
answers with one move, and `Haggle.play` clamps what comes back the way `Policy` clamps a price: an
unknown act is an offer, a price is bounded by the table, a quantity cannot exceed the cart, and
accepting means the terms that were actually offered. A negotiator may be wrong, rude or absurd;
the worst it can do is make a bad deal.

`colonysim/llm.py` is the worked example of a model doing it, through the official Anthropic SDK.
Nothing imports it and nothing in it runs unless `COLONYSIM_LLM=1` is set, so the package stays
standard library only and installs with no dependencies. It asks for one line per turn -- a
negotiation is a handful of calls, and they only happen when a cart arrives somewhere -- and every
failure falls back to the scripted negotiator, so the sim carries on with a worse haggler rather
than stopping. This is the "one model call per leg rather than per tick" the traders section
above always assumed.

## 4. Risk: what lives between the villages

Decided 2026-09-19 with Ryan: the risk to a caravan is **wolves and bears**, not bandits. Animals are
better than bandits here because they need no motive, no faction and no diplomacy — they are a
property of the terrain, which is the thing the roads already have to negotiate.

**Animals live in the land, not on the roads.** Wolf packs den in forest, bears in the rough country
above it, and nothing dens within a few tiles of a village. A den makes the ground around it dangerous,
falling off with distance. How risky a given road is is then just a sum along the tiles it happens to
run through — nothing marks a route as safe or unsafe, and moving a village or re-carving a road
changes the danger without anyone deciding that it should.

**Roads push back.** Hazard is divided down by road tier, and caravans passing within reach of a den
thin it while a quiet den recovers. So a trunk road wears into a safe road and a spur nobody uses stays
wild — which closes a loop with the road wear already in milestone 1, and gives a reason to invest in a
route beyond travel time.

**An encounter** is rolled once per day on the road. It ends in the caravan driving the animals off,
in a raid that takes part of the load — they come for the food and the cloth, not the stone — or, for a
bear, in the caravan turning round and going home with whatever it has left. That last case is the one
the design wanted from "simulated while travelling": arriving is not guaranteed, so a plan can fail.

**A trader answers the risk four ways,** all from the same number:

- **Route** — a dangerous leg costs more to consider, so the route search takes a longer, quieter chain
  of roads. This is the "minus risk" term the dispatch section above always assumed.
- **Load** — a caravan on a bad road goes out lighter, so there is less on the cart to lose.
- **Price** — what it carried through wolf country it asks a premium for, on top of the host's own
  price, capped at the usual price ceiling. A colony behind a wolf wood pays more for the same goods,
  which is the trade consequence of where it was built.
- **Guards** — a colony weighs what the animals are expected to take against what an escort costs per
  day, and hires when the sums favour it. This is the piece that makes the wild a reason to want coin
  rather than a flat tax on trading, and it is where the money system earns its keep.

**Accounting.** Animals are the only thing in the sim that destroys goods, and guard wages the only
coin that leaves it. Both are counted explicitly so that conservation is still checked to the last
decimal rather than loosened.

## 5. Population: people follow food

Decided 2026-09-19 with Ryan. Until this, a colony's population was set at founding and never moved,
which meant nothing the economy did had any stakes: a colony the caravans could not reach simply
went without, indefinitely, at no cost, and a colony swimming in food was no better off for it.
Population is now a live quantity, on one rule: **people follow food.**

- **A fed colony with stores to spare grows.** Being fed is not enough — the granary has to be above
  `PLENTY` (1.15 buffers) as well, so a village living hand to mouth stays the size it is. At full
  tilt growth is about a fifth over a 150-day run.
- **A colony that cannot feed everyone loses people,** judged over a fortnight rather than a day, so
  a caravan that is two days late does not kill anybody and a month of famine does.
- **A colony whose stores are merely thin loses a trickle** to the same instinct, before anyone goes
  hungry. Leaving is what you do before it gets bad.

**Eating is per head; the land is not.** Consumption follows the population exactly. Output follows
it only as far as `LAND_ELASTICITY` (0.7) allows, because the fields a village works do not get any
bigger when more people are born onto them. That gap is the ceiling: a colony grows into its own
land and then stops, and the only way past it is to buy food from somewhere with land to spare —
which is what the roads are for. It is also why a starving colony settles at a smaller size rather
than dying out, since shrinking improves what each remaining person gets.

**Population is who can walk the roads.** A caravan is a crew and guards are more people, and a
colony will not have more than `ROAD_SHARE` of itself away from home at once. So a colony that has
grown can run a second caravan, or run one and guard it, and not both; one that has been starved
down can do neither — except that it always keeps its one trip, or a colony could be locked out of
trading by the very smallness trading would fix.

**The claim this makes about trade is about people lost, not headcount.** A world that trades is not
always the larger one, because the colony that grew the food and sold it has less left to grow on.
What trade buys is that nobody has to die or walk out, and that is what is asserted across seeds.

`build_simulation(population=False)` freezes every colony at its founding size, the same way
`trade_enabled` and `stewards` do, and is the control case for all of the above.

## Milestones

1. World graph and carved roads, rendered, deterministic. No traders.
2. Reserve, surplus and prices on storage, with no movement. A headless multi-colony run verifies the
   economy math alone.
3. Scripted traders walking the roads and exchanging goods.
4. Agent-driven traders with negotiation dialogue. Built. A steward per colony reads the network
   and sets prices, reserves and labour (section 3a); when a cart arrives, the visitor and the host
   argue the price out a good at a time (section 3b). Scripted policies run both seams by default,
   and either can be replaced -- by a player, a rule, or a model -- without the rest of the sim
   knowing. `colonysim/llm.py` is the worked example of the model case, off unless switched on.
5. Risk and texture: wild animals on the roads, weather closing routes, reputation between colonies,
   road wear and upgrade. Road wear, the animals and reputation are built; weather is not.
6. Population following food (section 5), so the economy has stakes: colonies grow or shrink with
   their stores, and how many people a colony has decides what it eats, what it makes, and how many
   caravans and guards it can put on the road. Built.

## How we know it works

A headless multi-day run across several colonies, asserting:

- every settlement is reachable from every other one on the road graph;
- **conservation** — total goods in the world change only by production, consumption, and what the
  animals take, never by trade. A rounding bug in the exchange that mints or eats goods is the single
  most likely defect here;
- price variance for a given good across colonies falls over the run — proof that trade is doing its job;
- no caravan is stuck: every dispatched trader either arrives, returns, or dies for a stated reason;
- **no negotiator is ever talked past its own limit**, and a deal is struck exactly when the two
  limits overlap — checked over a grid of limits and temperaments, because that property is what
  keeps a bad haggler (or a model having an off day) from wrecking a colony;
- **cutting a world off from trade costs it people** — across seeds, a world with the traders taken
  off loses more to hunger and emigration than the same world with them on. This is the assertion
  that says the economy has stakes;
- colonies neither explode nor collapse over 150 days under default settings: every village ends
  recognisably like itself, and the world's population inside a band either side of what it started
  with.

## Open questions

- How many settlements, and are the non-player ones simulated at full fidelity or abstracted to
  production and consumption rates? Abstracting them is much cheaper and probably invisible.
- Does the player's colony trade through exactly the same code path? It should — one economy, no
  special case.
- ~~Is a caravan simulated while travelling, or resolved on arrival?~~ Settled: travelling is simulated
  day by day, which is what lets the animals meet a caravan on the road.
- ~~Do traders carry currency, or is it pure barter?~~ Settled: currency, falling back to barter for
  whatever the purse will not cover.

## Related pages

- `project-direction.md` — decision 3, autonomous visitor agents, which the agent-driven trader extends.
- `brainstorm-options.md` — Option 5, visitor agents.
