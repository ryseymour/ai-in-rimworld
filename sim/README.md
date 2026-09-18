# colonysim

World generation and procedural roads for the colony simulation. Stdlib only,
no dependencies, so it ports into the sim proper as a module.

See `../wiki/design-inter-colony-trade.md` for the design this implements. This
is step 1 of it: the road network. Storage, prices and traders come next.

## Try it

```
python -m colonysim.demo --seed 7 --width 78 --height 30
```

Glyphs: `~` water, `.` plains, `"` forest, `^` rough; `:` foot path, `-` dirt
road, `=` paved; digits are settlements.

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

## Tests

```
python -m pytest tests -q
```

They assert what the design calls for: every settlement reachable, generation
deterministic, routes sharing tiles rather than running parallel, roads not
ploughing through water, and tier promotion and decay.
