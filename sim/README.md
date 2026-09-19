# colonysim

World generation, procedural roads and an economy for the colony simulation.
Stdlib only, no dependencies, so it ports into the sim proper as a module.

See `../wiki/design-inter-colony-trade.md` for the design this implements:
roads, storage and prices, traders moving goods between colonies, a steward
running each colony's side of it, and a population that grows or shrinks with
what the colony has to eat.

## Open it in a browser

```
python3 -m colonysim.server
```

Then open **http://127.0.0.1:7700**. The map draws the terrain, the road
network, every colony and the caravans moving between them, with what each one
is carrying and every colony's shelves updating beside it. The Stewards panel
underneath shows what each colony has decided to do about its own prices --
`food x1.32` is a colony bidding for supply, `wood x0.71` one discounting to
shift a pile -- along with the last thing it changed and why. **At the counter**
under it shows the last few arguments over a price, line by line, as caravans
arrive and haggle. Wolf packs and bear territories are the coloured patches the roads have to get past; a caravan with
a ring around it has hired guards. Pause and speed controls are on the page.
Ctrl-C in the terminal stops it.

The colony table carries each village's headcount with an arrow for which way
it has gone since it was founded, and the header counts everyone alive.

Three colonies by default, which is small enough to follow every trade.
`--settlements 6` gives the wider world, and `--no-stewards` takes the decision
makers off so you can see what the same world does on bare scarcity. The
Standing panel under the stewards is what each colony makes of the others --
`Coldhollow -> Brackwater trusted +0.81`, with the last thing that moved it
underneath -- and the header counts caravans turned away at a gate.

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
has on its shelves. Ctrl-C to stop. `--delay 0.4` slows it down, `--delay 0`
runs flat out, `--seed` gives a different world.

## Compare it

```
python -m colonysim.demo --seed 23 --days 150
```

Runs the world for 150 days with traders, then runs the same world again with
trade switched off, and prints both so the difference is visible.

Glyphs: `~` water, `.` plains, `"` forest, `^` rough; `:` foot path, `-` dirt
road, `=` paved; `w` a wolf pack and `B` a bear; digits are settlements, `@` is
a caravan.

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

## Haggling

A sale is not arithmetic any more. When a cart pulls up, the visitor and the
host argue a good at a time, in `negotiation.py`, and the price is whatever
they agree on.

Each side has two numbers. A **limit** it will not cross: for the host, its own
price plus whatever the road was worth, capped at what the good can fetch there
-- which is exactly the price the sim used to charge outright, so the old
take-it-or-leave-it figure is now the *most* a host can be talked into. For the
trader, what the cargo was worth at home when it was loaded, because below that
it is better off carting the goods back. And an **opening**, nowhere near it.
They take turns: each turn a side either takes what is on the table or names a
price a little closer to the other's, and by its last turn everyone is standing
on their own limit, so it always ends.

What differs between two negotiators is how fast they give that ground away.
A host four days from an empty granary concedes early and pays for it; one
merely topping up holds out and pays less, and buys less of it at a price it
dislikes. A trader carrying goods that were nearly this dear at home has
nothing to give and holds firm. So the same cargo at the same counter fetches
different prices depending on who needs it, and you can read why in what was
said.

A deal is struck exactly when the two limits overlap, and never outside them.
When they do not, the goods stay on the cart and go home -- a trip that did not
pay, which the sim had no way to express before. In practice that is rare (one
journey in a couple of hundred) because a caravan only sets out when the sums
looked good.

The browser viewer shows the last few arguments under **At the counter**, and
`python -m colonysim.demo` prints the most recent one:

```
  day 143, over wood
    Coldhollow: 10 wood, straight off the road. 1.31 the unit.
    Brackwater: Say 1.01 and we will take 10 off you.
    Coldhollow: That will do. 1.01.
  Brackwater took 10 wood from Coldhollow at 1.01
```

Nothing here is random: the same seed replays the same argument word for word.

### Letting something else do the talking

`bargain` is the scripted negotiator, and `Steward.negotiator` is where you
replace it -- the same seam as `decide`, one level down. `decide` is the stance
a colony takes over weeks; `negotiator` is how it argues a single sale.

```python
from colonysim import Move

def stubborn(haggle, side):
    seat = haggle.seat(side)
    return Move(side, "counter", seat.limit, seat.want, "my price or no price.")

sim.stewards[0].negotiator = stubborn
```

Whatever is talking sees `Haggle.brief(side)` -- its own position, its limit,
what has been offered and everything said so far -- and answers with one move.
`Haggle.play` clamps whatever comes back: an unknown act becomes an offer, a
price is bounded by the table, a quantity cannot exceed the cart, and accepting
means the terms that were actually offered rather than terms invented while
accepting. So a negotiator can be wrong, rude, or absurd, and the worst it can
do is make a bad deal.

`colonysim/llm.py` is the worked example of a model doing it. Nothing imports
it, and nothing in it runs unless `COLONYSIM_LLM=1` is set, so the package
stays standard library only and installs with no dependencies:

```python
from colonysim.llm import claude_negotiator

for steward in sim.stewards:
    steward.negotiator = claude_negotiator()   # needs `pip install anthropic`
```

It asks for one line per turn, so a negotiation is a handful of calls and they
only happen when a cart actually arrives somewhere. Every failure -- no key, no
package, a timeout, a reply nobody can parse -- falls back to `bargain`, so the
sim carries on with a worse negotiator rather than stopping. `speaker_from` is
the general form: anything that turns a prompt into a line of text is a
negotiator, including a player's own UI or a local model.

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

## Standing

Every colony keeps one number about every other colony it has dealt with, from
-1 (shunned) to +1 (trusted), and nothing sets it directly. It is written by
conduct at the counter (`reputation.py`):

* a parcel sold at the host's own price, or a bill covered in full, earns a
  little goodwill -- most of the trust in the world is made of ordinary deals
  done properly;
* a trader that argues its way well above the host's own price is remembered
  as gouging, in proportion to how far over and how big the deal was -- so
  what the haggling seam does with the room it is given is itself conduct. A
  modest premium for a dangerous road is not gouging: traders have to be able
  to charge for the wolves.
* a buyer who runs out of both coin and goods to barter and walks away owing
  picks up a credit mark -- light on purpose, because a colony only fails to
  cover a bill when it is broke rather than dishonest, and this sim cannot
  tell those apart. It makes a colony a worse customer, not an outcast;
* being turned away at a gate is remembered too, by the colony that was turned
  away.

Four things read it back, so conduct has a price:

* **the counter** -- standing is what the host brings to the table before
  anyone opens their mouth. A trusted caravan argues over a range that starts
  above the colony's own asking price and is charged below it for what it
  takes home; a distrusted one sits down against a range that is already
  narrower. It does not change how either side haggles, only what there is to
  haggle over;
* **where caravans go** -- a colony's one caravan is steered toward the
  partners it thinks well of, because that is where the prices are better;
* **guards** -- two colonies that both trust each other share an escort and
  split the wage;
* **the gate** -- below `EMBARGO` (-0.55) a colony will not deal at all, in
  either direction: it sends nobody there and turns their caravans away.

Standing fades toward neutral by 0.3% a day, so half of a grudge is still
there eight months later. That is the lasting part: a colony that gouged its
way through one winter is still paying worse prices the following autumn, and
still has a way back if it behaves. `build_simulation(reputation=False)` leaves
every colony a permanent stranger to every other, which is the control case.

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

On arrival the caravan does not sell at the host's prices -- it argues about
them (below), then spends the proceeds on what home is short of, then goes
home.

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

328 tests. Roads: every settlement reachable, generation deterministic, routes
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

Standing: the ledger itself (clamped, written down with its reason, faded by
time alone), what each kind of conduct is worth, the counter pricing the same
goods differently for a trusted and a distrusted caravan without minting any,
the caravan turned away at a shut gate, a steward that stops bidding for a
supplier it would not let in, and the whole arc end to end -- gouge a colony
visit after visit until it closes its gate, then a year of quiet before it
opens again. Over 250 days on four seeds an honest world turns nobody away.

Wildlife: dens only on ground that suits them and never beside a village,
danger falling off with distance, better roads and busier roads being safer,
a raid taking exactly what leaves the cargo and never more than is on the
cart, guards paying for themselves in goods saved, a trader taking the long
way round a den, and — over 120 days on four seeds — the animals costing the
roads something without starving anybody or shutting trade down.
