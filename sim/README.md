# colonysim

World generation and procedural roads for the colony simulation. Stdlib only,
no dependencies, so it ports into the sim proper as a module.

See `../wiki/design-inter-colony-trade.md` for the design this implements:
roads, storage and prices, and traders moving goods between colonies.

## Watch it

```
python -m colonysim.watch --seed 23
```

Redraws the map once per day with caravans (`@`) moving along the roads, and
under it what each one is carrying, where it is headed, and what every colony
has on its shelves. Ctrl-C to stop. `--delay 0.4` slows it down, `--delay 0`
runs flat out, `--seed` gives a different world.

## Compare it

```
python -m colonysim.demo --seed 23 --days 150
```

Runs the world for 150 days with traders, then runs the same world again with
trade switched off, and prints both so the difference is visible.

Glyphs: `~` water, `.` plains, `"` forest, `^` rough; `:` foot path, `-` dirt
road, `=` paved; digits are settlements, `@` is a caravan.

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
| price gap, tools | 6.33 | 23.72 |
| colonies out of food | nobody | Brackwater, Eastmoor |

Stone often stays put: it is heavy and cheap, so a caravan of it rarely clears
the cost of the journey. That is the economy working, not a bug — but
`MIN_TRIP_WORTH`, and stone's `bulk` and `base_price` in `goods.py`, are the
knobs if it should move.

## Tests

```
python -m pytest tests -q
```

81 tests. Roads: every settlement reachable, generation deterministic, routes
sharing tiles rather than running parallel, roads not ploughing through water,
tier promotion and decay. Economy: reserves and prices, the purse refusing to
overdraw, barter never digging into the reserve, no cargo loaded that the
destination will not buy. And over a 150-day run on four seeds — **goods and
coin are exactly conserved** (trade must never mint or destroy either), trade
narrows the price gap against the no-trade control, nobody starves who would
have starved without it, and no caravan is left stranded on the road. The
viewer: a journey's tiles join into one contiguous run, and a caravan is always
somewhere on its own road.
