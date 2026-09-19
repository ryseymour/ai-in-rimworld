# colonysim

World generation and procedural roads for the colony simulation. Stdlib only,
no dependencies, so it ports into the sim proper as a module.

See `../wiki/design-inter-colony-trade.md` for the design this implements:
roads, storage and prices, and traders moving goods between colonies.

## Try it

```
python -m colonysim.demo --seed 23 --days 150
```

That generates a world, runs it for 150 days with traders on the roads, and
runs the same world again with trade switched off so the two can be compared.

Glyphs: `~` water, `.` plains, `"` forest, `^` rough; `:` foot path, `-` dirt
road, `=` paved; `w` a wolf pack and `B` a bear; digits are settlements.

## How roads are generated

1. **Candidate connections** — the Gabriel graph over settlement positions,
   plus each village's 3 nearest neighbours. Gabriel rejects an edge when a
   third village sits inside the circle it spans, which drops the long crossing
   edges that would otherwise web the map.
2. **Which to keep** — a minimum spanning tree over terrain-aware path costs
   guarantees every village is reachable. Then the worst detours among the
   rejected candidates are added back (25% by default) so the network has loops
   and alternate routes rather than one path to anywhere.
3. **Where each road runs** — A* over the terrain, with slope penalised far
   more heavily than distance (`SLOPE_WEIGHT` in `terrain.py`). That one term
   is most of what makes roads follow valleys instead of running ruler-straight.
4. **Why roads bundle** — a tile that already carries road costs `ROAD_REUSE`
   (0.28) of normal, so later routes bend to join earlier ones. Routes are
   carved busiest-first, ordered by exact edge betweenness on the tree, so the
   trunks exist before the traffic that should merge onto them.

Everything is seeded: the same world always regenerates the same roads.

## Wear

`apply_traffic` promotes tiles through foot path → dirt road → paved as
caravans use them; `decay` grasses them back over when they go unused. Trade
routes that get used become visibly better roads.

## What lives out there

Wolves and bears are placed in the terrain, not on the roads: wolves den in
forest, bears in the rough country above it, and nothing dens within six tiles
of a village. A den makes the ground around it dangerous, falling off with
distance, so how risky a road is falls out of where it happens to run.

Two things make a road safer. Its tier: a paved trunk road carries under a
third of the hazard of the foot path beside it. And traffic: caravans passing
within reach of a den push it back, while a quiet den grows again. So a busy
route wears into a safe route, and a spur nobody uses stays wild.

A caravan rolls once a day against the hazard of the road it is on. It can
drive the animals off -- which thins the den -- or be raided, losing part of
its load. Animals go for the food and the cloth; stone is not worth their
trouble. A bear is met less often than wolves but is far worse when it is: it
can turn a caravan around and send it home half-loaded, the trip wasted.

Animals are the only thing in the sim that destroys goods, and guard wages the
only coin that leaves it, so both are counted (`Simulation.lost` and
`escort_wages`) and conservation is checked against them.

## How traders answer the wild

Four responses, all falling out of the same hazard number:

* **Route.** A dangerous leg costs more to consider, so the route search takes
  a longer, quieter chain of roads instead of the short way through the trees.
* **Load.** A caravan on a bad road goes out lighter -- there is simply less on
  the cart to lose.
* **Price.** What it carried through wolf country it asks a premium for, on top
  of the host's own price. A host short of the good wears it; nobody pays above
  the usual price ceiling, so the premium is a thin margin, not a hold-up.
* **Guards.** A colony compares what the animals are expected to take against
  what an escort costs per day, and pays when the sums favour it. Guards make
  the animals much likelier to keep their distance and cut what they get away
  with. So the wolves are a reason to want coin, rather than a flat tax.

The decision to travel is made on the same terms: expected loss comes off the
worth of the trip, so a marginal journey down a wolf road is not made at all.

`build_simulation(..., wildlife=False)` gives the same world with the animals
taken off it, which is the control for every claim above.

## How the economy works

**What a colony makes** is its own consumption scaled by how good the land
around it is at each good, so a village ringed by forest has wood to spare and
buys its stone. World totals are then calibrated to cover world consumption:
the point is to test distribution, since a world in deficit starves whatever
the traders do.

**Storage is the whole trade interface.** Per good, a colony holds back a
reserve — its consumption times that good's buffer in days. Everything above
the reserve is for sale; everything below it is what the colony will buy.
Nothing else defines the market.

**Price** comes from the same number: `base × 3 / (1 + 2 × stock/reserve)`,
floored at 0.35× and capped at 3×. An empty store pays the ceiling, a store
sitting exactly on its reserve pays the base price, and a glut tails off to the
floor. Two colonies therefore quote different prices for the same good, and
that gap is what a trader earns. As goods move the gap closes, so the economy
settles itself with nothing scripting it.

## How trade works

A colony runs one caravan at a time. It scores every colony it can reach on the
road network — not just its neighbours — on what a trip there would be worth
per day of travel, then loads the best cargo it can out of its surplus and
sends it.

Two things it works from are deliberately imperfect. It plans against
`MarketView`, its memory of what a market looked like when a caravan last came
back, which may be weeks stale. And that memory holds what was *for sale*, not
just the price, because a colony sitting exactly on its reserve quotes a
perfectly ordinary price while having nothing whatever to sell.

On arrival the caravan sells what the host is short of, at the host's prices,
then spends the proceeds on what home is short of, then goes home.

**Settlement is in currency, falling back to barter.** The buyer pays from its
purse as far as the purse goes. Whatever is left it covers in goods out of its
own surplus, valued at its own prices at the moment each parcel changes hands.
So a colony rich in goods and poor in coin can still trade, and what it barters
becomes the caravan's return load. Currency is its own object, so a second one
can be added later at a rate without the trade code caring.

Journeys wear the roads they use, and a worn road is faster, which makes it
more attractive, which wears it further.

## What it does

`--seed 23`, 150 days, the same world with and without traders:

| | with trade | without |
|---|---|---|
| price gap, food | 1.51 | 5.30 |
| price gap, tools | 5.15 | 23.66 |
| colonies out of food | nobody | Coldhollow, Eastmoor, Fenwick |

And what the animals cost that same world over 150 days:

| | |
|---|---|
| journeys made | 65 (76 with no animals on the map) |
| met on the road | 14 |
| raided | 4 |
| taken by animals | 4 food |
| paid to guards | 246 coin |

Stone often stays put: it is heavy and cheap, so a caravan of it rarely clears
the cost of the journey. That is the economy working, not a bug — but
`MIN_TRIP_WORTH`, and stone's `bulk` and `base_price` in `goods.py`, are the
knobs if it should move.

## Tests

```
python -m pytest tests -q
```

123 tests. Roads: every settlement reachable, generation deterministic, routes
sharing tiles rather than running parallel, roads not ploughing through water,
tier promotion and decay. Economy: reserves and prices, the purse refusing to
overdraw, barter never digging into the reserve, no cargo loaded that the
destination will not buy. And over a 150-day run on four seeds — **goods and
coin are exactly conserved** (trade must never mint or destroy either), trade
narrows the price gap against the no-trade control, nobody starves who would
have starved without it, and no caravan is left stranded on the road.

Wildlife: dens only on ground that suits them and never beside a village,
danger falling off with distance, better roads and busier roads being safer,
a raid taking exactly what leaves the cargo and never more than is on the
cart, guards paying for themselves in goods saved, a trader taking the long
way round a den, and -- over 120 days on four seeds -- the animals costing the
roads something without starving anybody or shutting trade down.
