# colonysim

World generation, procedural roads and an economy for the colony simulation.
Stdlib only, no dependencies, so it ports into the sim proper as a module.

See `../wiki/design-inter-colony-trade.md` for the design this implements:
roads, storage and prices, traders moving goods between colonies, a steward
running each colony's side of it, a population that grows or shrinks with what
the colony has to eat, and a year of seasons and weather over all of it.

## Open it in a browser

```
python3 -m colonysim.server
```

Then open **http://127.0.0.1:7700**. The map draws the terrain, the road
network, every colony and the caravans moving between them, with what each one
is carrying and every colony's shelves updating beside it. The chip at the top
left says where in the year you are and what the sky is doing, and the dots
beside it are the week ahead -- each `!` a day of weather bad enough to be
worth planning around. A road the weather has shut is crossed through in red,
and a caravan sitting out a storm turns red where it stands. The Stewards panel
underneath shows what each colony has decided to do about its own prices --
`food x1.32` is a colony bidding for supply, `wood x0.71` one discounting to
shift a pile -- along with the last thing it changed and why. Wolf packs and bear
territories are the coloured patches the roads have to get past; a caravan with
a ring around it has hired guards. Pause and speed controls are on the page.
Ctrl-C in the terminal stops it.

The colony table carries each village's headcount with an arrow for which way
it has gone since it was founded, and the header counts everyone alive.

Three colonies by default, which is small enough to follow every trade.
`--settlements 6` gives the wider world, `--no-stewards` takes the decision
makers off so you can see what the same world does on bare scarcity, and
`--no-weather` puts it under an endless temperate sky with no seasons at all.

No dependencies and no build step — it is `http.server` and one HTML page. If
7700 is already taken it moves to the next free port and tells you which, so it
can sit alongside something else already using that number. `--seed` gives a
different world, `--speed` sets days per second.

## Watch it in the terminal

```
python -m colonysim.watch --seed 23
```

Redraws the map once per day with caravans (`@`) moving along the roads, and
under it what each one is carrying, where it is headed, and what every colony
has on its shelves. The line under the map is the date, today's sky, the week
ahead as one glyph a day, and any route the weather has shut. Ctrl-C to stop.
`--delay 0.4` slows it down, `--delay 0` runs flat out, `--seed` gives a
different world, `--no-weather` takes the year off it.

## Compare it

```
python -m colonysim.demo --seed 23 --days 180
```

Runs the world for 180 days -- three years -- with traders, then runs the same
world again with trade switched off, with nobody minding the shop, with no
animals, and under an endless temperate sky, and prints all of them so each
difference is visible on its own. The last table is the shape of the year.

Glyphs: `~` water, `.` plains, `"` forest, `^` rough; `:` foot path, `-` dirt
road, `=` paved; `w` a wolf pack and `B` a bear; digits are settlements, `@` is
a caravan.

## The year

Sixty days, four seasons of fifteen. Everything about it falls out of two
tables in `weather.py`.

**The land works to a calendar.** Each season multiplies what a colony's land
gives it, per good. Autumn is the harvest -- nearly twice the food -- and
winter makes almost none of anything except tools, which is indoor work and
barely notices. The four multipliers for any one good average to exactly one,
so a year produces what the land would have produced anyway; the seasons only
decide *when*. Nothing else needs telling: prices in this sim are a function of
what is on the shelves, so a harvest glut cuts the price of food and a winter
empties the store and puts it back up.

The year that comes out of that is not quite the obvious one. Food is cheapest
in autumn and dearest in **spring** -- a colony goes into winter on a full
granary and comes out the far side on an empty one, so the hungry gap is after
the cold rather than during it.

**Weather is a property of the day**, not of a place: one sky over the whole
map, in spells of a few days rather than flickering, drawn from the season's
own table. Blizzards are a winter thing, mud a spring one, and autumn is storm
season.

**A road's own grade is what shelters it.** Weather slows a route in proportion
to how poor the road is, and a few kinds shut it outright below a grade they
name:

| | slows | shuts |
|---|---|---|
| rain, mud, heat | a little | nothing |
| snow | a foot path takes nearly two days to walk a day of | nothing |
| storm | yes | a bare foot path |
| blizzard | most | anything short of a finished dirt road |

Nothing ever shuts a paved road. So **paving your trunk route is what buys you
a winter economy**: on a young map, where every road is still a foot path, a
storm closes the lot and everyone waits; on a worn one the trunk keeps trading
while the spurs are shut, and the traffic that wears the trunk in is the same
traffic the closures push onto it.

A closed leg is taken *out* of the route graph rather than made expensive, so
the search finds whatever open chain is left -- a snowed-in pass pushes a
caravan onto the long valley road instead of stopping it. A caravan already out
there makes no progress at all on a day its road is shut: it sits the storm out
and arrives late, and its ledger says so (`waited out the blizzard`). The
animals still get their roll while it waits; a camped caravan is not a safe
one.

**The forecast is exact.** Weather is generated forward and then fixed, so
asking on day 35 what day 40 looks like gives the answer day 40 will really
have. That is deliberate: a trader here is already wrong about markets and
wrong about wolves, and making it wrong about the sky too would only blur what
the seasons are doing. Traders decide on it -- a trip the coming week will drag
out loses to one it will not -- and a steward reads it off `NetworkView`:

```python
view = sim.network_view(0)
view.date            # early autumn, year 2
view.weather.name    # 'storm'
view.forecast        # the next seven days, exactly as they will happen
view.open_links()    # who is reachable today
view.shut()          # who the weather has cut off
```

A shut neighbour stays on the map rather than vanishing from the view: a
steward that cannot see a snowed-in village cannot plan for the thaw.

**And the stewards act on it.** Through autumn, `coming_season` says winter, so
the scripted merchant deepens its granary for everything winter will not make.
That does two things at once: it stops the colony selling what it is about to
need, and -- because scarcity is measured against the reserve -- it puts the
price up until somebody hauls more in. Autumn is when everybody buys food.

The upshot is that a year of weather does not simply mean less trade. It
usually means *more* journeys than the same world under a flat sky, moved
around the calendar: fewer in winter, and a rush before it.

Weather costs the roads time and never costs anyone goods. The animals are
still the only thing in this sim that destroys anything, so conservation is
checked to the last decimal with a calendar in the world exactly as it was
without one. `build_simulation(..., weather=False)` gives the same world with
no year in it at all, which is the control for every claim above.

## Stewards

Each colony has one: the agent that runs its side of the economy. A steward
sees the trade network -- who it can reach, how far and how dangerous the road
is today, and what the last caravan home reported about each market -- and
changes three things about its own colony:

* **prices**, as a markup on what scarcity alone would ask (0.6x to 1.8x). The
  same number is what a visiting caravan is paid here and what this colony pays
  for imports, so bidding for supply costs real coin and discounting to shift a
  glut earns less per unit.
* **the reserve**, how many days of a good it keeps back, which is the line
  between what it sells and what it wants to buy.
* **where its people work**, a lean on the land's own output, rebalanced so no
  labour is created -- terrain still decides what a village is any good at.

The scripted steward (`merchant` in `steward.py`) bids up what it is short of,
working backwards from what a trader would need to see before making the trip;
undercuts whoever else could supply the colony that wants what it has spare;
and over weeks moves people toward what it keeps running out of. It is
deliberately a thin function over the view: pass `decide=` to `Steward` and
anything else can run a colony instead, off the same `NetworkView` and the same
clamped setters. `Steward.brief()` writes the whole situation out as text for
exactly that.

```python
sim = build_simulation(seed=23, settlements=3)
steward = sim.stewards[0]
steward.set_markup("food", 1.4, "we are short and the road is long")
steward.set_reserve_days("wood", 20)
print(steward.brief())
```

## People

A colony's population is a live number, and it follows one thing: food.

* **Fed, with stores to spare** — it grows, slowly. Being fed is not enough;
  the granary has to be above 1.15 buffers as well, so a village living hand to
  mouth stays the size it is. At full tilt that is about a fifth over 150 days.
* **Unable to feed everyone** — it loses people, judged over a fortnight rather
  than a day, so a caravan two days late kills nobody and a month of famine
  does.
* **Stores merely thin** — a trickle leaves before anyone goes hungry.

**Eating is per head; the land is not.** Twice the people eat twice as much and
do not harvest twice as much, because the fields did not get any bigger
(`LAND_ELASTICITY` in `people.py`). That gap is the ceiling a colony grows into
— past it, the only way to feed more people is to buy food from somewhere with
land to spare, which is what the roads are for. It is also why a starving
colony settles at a smaller size instead of dying out.

**Population is also who can walk the roads.** A caravan is a crew, guards are
more people, and a colony will not have more than a fifth of itself away from
home at once. So a village that has grown can run a second caravan, or run one
and guard it, and not both; a village that has been starved down can do neither
— except that it always keeps its one trip, or a colony could be locked out of
trading by the very smallness trading would fix.

The claim this makes about trade is about people lost, not headcount: a world
that trades is not always the larger one, since the colony that grew the food
and sold it has less left to grow on. What trade buys is that nobody has to die
or walk out. `python -m colonysim.demo` prints both sides of that, and
`build_simulation(..., population=False)` freezes every colony at its founding
size as the control.

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
the traders do. Both sides of that move with the population afterwards — see
**People** above for how far each one follows it.

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

A colony runs as many caravans at once as it has people to crew — usually one,
two once it has grown. It scores every colony it can reach on the
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

`--seed 23`, 180 days -- three years -- the same world with and without traders:

| | with trade | without |
|---|---|---|
| price gap, cloth | 4.55 | 5.99 |
| price gap, tools | 0.45 | 0.71 |
| colonies out of food | nobody | Coldhollow |

And the shape of one of those years, summed over the three:

| season | food made | mean food price | journeys home | days a road was shut |
|---|---|---|---|---|
| spring | 1826 | 2.15 | 3 | 2 |
| summer | 2772 | 2.03 | 4 | 7 |
| autumn | 4259 | 1.73 | 3 | 10 |
| winter | 480 | 1.84 | 0 | 7 |

Nine times as much food is grown in autumn as in winter, the price tracks it
down and back up, and in this three-colony world -- where the roads never get
busy enough to wear past a foot path -- winter trade stops altogether. On a
map with six colonies the trunk roads reach dirt and the winters stay open.

Stone often stays put: it is heavy and cheap, so a caravan of it rarely clears
the cost of the journey. That is the economy working, not a bug — but
`MIN_TRIP_WORTH`, and stone's `bulk` and `base_price` in `goods.py`, are the
knobs if it should move.

## Drawing the roads in another UI

If you already have a renderer -- a game map, a minimap, a build-mode overlay
-- two calls give you the roads as plain JSON-safe data, so nothing on your
side has to import from this package:

```python
from colonysim import build_simulation, road_links, road_overlay

sim = build_simulation(seed=23)
road_overlay(sim.network)          # every road tile: x, y, tier, speed
road_links(sim.network, sim.world) # one line per route: endpoints and tier
```

`road_overlay` is per tile, for anywhere the map is drawn at tile resolution.
`road_links` is one line per route between two settlements, for anywhere too
small for individual tiles to read -- a minimap, where 120 separate road tiles
are noise but the shape of the network is the point. Weight the line by `tier`:
1 is a foot path, 2 a dirt road, 3 paved.

Both follow real wear, so a route that gets busy shows up as a better road in
whatever is drawing it.

## Tests

```
python -m pytest tests -q
```

298 tests. Roads: every settlement reachable, generation deterministic, routes
sharing tiles rather than running parallel, roads not ploughing through water,
tier promotion and decay. Economy: reserves and prices, the purse refusing to
overdraw, barter never digging into the reserve, no cargo loaded that the
destination will not buy. And over a 150-day run on four seeds — **goods and
coin are exactly conserved** (trade must never mint or destroy either), trade
narrows the price gap against the no-trade control, nobody starves who would
have starved without it, and no caravan is left stranded on the road. The
viewers: a journey's tiles join into one contiguous run, a caravan is always
somewhere on its own road, and the server is exercised over real HTTP — routes,
pause, speed, and falling back off a busy port.

Wildlife: dens only on ground that suits them and never beside a village,
danger falling off with distance, better roads and busier roads being safer,
a raid taking exactly what leaves the cargo and never more than is on the
cart, guards paying for themselves in goods saved, a trader taking the long
way round a den, and — over 120 days on four seeds — the animals costing the
roads something without starving anybody or shutting trade down.

The year: a year's growth multipliers averaging to exactly one so a calendar
cannot quietly recalibrate the world, a season's worth of days landing in
exactly one season, a worse road losing more to the same weather and a paved
one never being shut at all, a shut leg being no way through rather than a dear
one, the forecast matching what actually happens whether you ask early or walk
to it, blizzards staying in winter over twenty years of them, and — over
several years on four seeds — the harvest landing in autumn, food being dearest
in the spring hungry gap, goods and coin still conserved to the last decimal
with weather in the world, and nobody left stranded on a closed road. Plus the
controls: `weather=False` leaves no date in a steward's view and no road ever
shut, and a steward with no calendar keeps exactly the buffers it kept before
there was a year.
