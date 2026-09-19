"""Generate a world, run it, and print what happened.

    python -m colonysim.demo --seed 23 --days 150
"""
from __future__ import annotations

import argparse

from .goods import GOOD_NAMES
from .render import legend, render
from .simulation import build_simulation
from .weather import SEASONS, YEAR_DAYS


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a world and trade across it.")
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--width", type=int, default=90)
    ap.add_argument("--height", type=int, default=45)
    ap.add_argument("--settlements", type=int, default=3)
    ap.add_argument("--days", type=int, default=180, help="three years by default")
    ap.add_argument("--journeys", type=int, default=6, help="journeys to print")
    args = ap.parse_args()

    sim = build_simulation(args.seed, args.settlements, args.width, args.height)
    control = build_simulation(args.seed, args.settlements, args.width, args.height)
    control.trade_enabled = False
    # The same world with nobody running the colonies: prices come off the
    # shelves and nothing else. The control case for what stewards do.
    unled = build_simulation(
        args.seed, args.settlements, args.width, args.height, stewards=False
    )
    # The same world with the wolves and bears taken off it, so the cost of
    # the wild can be read straight off the difference.
    tame = build_simulation(
        args.seed, args.settlements, args.width, args.height, wildlife=False
    )
    # And the same world under an endless temperate sky, which is the control
    # for the year: no harvest, no winter, and no road ever shut.
    calm = build_simulation(
        args.seed, args.settlements, args.width, args.height, weather=False
    )

    sim.run(args.days)
    control.run(args.days)
    unled.run(args.days)
    tame.run(args.days)
    calm.run(args.days)

    print(render(sim.world, sim.network, wilds=sim.wilds))
    print()
    print(legend(sim.world, sim.network, sim.wilds))

    print(f"\n--- after {args.days} days, {sim.journeys} journeys ---\n")
    print(f"{'colony':<12}{'food':>9}{'wood':>9}{'stone':>9}{'cloth':>9}{'tools':>9}{'coin':>10}")
    for colony in sim.colonies:
        row = "".join(f"{colony.storage.get(g):>9.0f}" for g in GOOD_NAMES)
        print(f"{colony.name:<12}{row}{colony.purse.amount:>10.0f}")

    print("\nprice gap between the dearest and cheapest colony:")
    print(f"  {'good':<8}{'with trade':>12}{'without':>12}{'no steward':>12}")
    for good in GOOD_NAMES:
        print(
            f"  {good:<8}{sim.price_spread(good):>12.2f}"
            f"{control.price_spread(good):>12.2f}{unled.price_spread(good):>12.2f}"
        )

    hungry = sim.hungry_colonies()
    starved = control.hungry_colonies()
    print(f"\nout of food, with trade: {', '.join(hungry) or 'nobody'}")
    print(f"out of food, without:    {', '.join(starved) or 'nobody'}")

    print("\n--- the stewards ---\n")
    for steward in sim.stewards:
        stance = steward.stance()
        print(f"  {steward.name}")
        asking = ", ".join(
            f"{good} {at:.2f}x" for good, at in stance["markup"].items()
        )
        holding = ", ".join(
            f"{good} {steward.colony.reserve_days(good):.0f}d" for good in stance["reserve"]
        )
        working = ", ".join(f"{good} {at:.2f}x" for good, at in stance["focus"].items())
        print(f"    asking:  {asking or 'whatever the shelves say'}")
        print(f"    holding: {holding or 'the usual buffers'}")
        print(f"    working: {working or 'whatever the land gives'}")
        for line in steward.log[-2:]:
            print(f"    {line}")

    print(f"\n  out of food with stewards: {', '.join(sim.hungry_colonies()) or 'nobody'}")
    print(f"  out of food without them:  {', '.join(unled.hungry_colonies()) or 'nobody'}")
    print(f"  journeys: {sim.journeys} with stewards, {unled.journeys} without")

    print(f"\n--- the wild ---\n")
    print(f"  journeys made:      {sim.journeys}  (a tame world: {tame.journeys})")
    print(f"  met on the road:    {sim.meetings}")
    print(f"  raided:             {sim.raids}")
    print(f"  turned back:        {sim.journeys_turned_back}")
    lost = ", ".join(f"{q:.0f} {g}" for g, q in sorted(sim.lost.items()) if q >= 0.5)
    print(f"  taken by animals:   {lost or 'nothing'}")
    print(f"  paid to guards:     {sim.escort_wages:.0f} coin")

    print(f"\n--- the year ---\n")
    years = args.days / YEAR_DAYS
    print(f"  {args.days} days is {years:.1f} years of {YEAR_DAYS}.")
    print(
        f"  {'season':<9}{'days':>6}{'food made':>11}{'food price':>12}"
        f"{'journeys':>10}{'shut days':>11}{'days waited':>13}"
    )
    for season in SEASONS:
        tally = sim.tallies.get(season.name)
        if tally is None:
            continue
        print(
            f"  {season.name:<9}{tally.days:>6}{tally.produced.get('food', 0.0):>11.0f}"
            f"{tally.mean_price('food'):>12.2f}{tally.journeys:>10}"
            f"{tally.shut_days:>11}{tally.waited:>13.0f}"
        )
    print(
        f"\n  journeys: {sim.journeys} through the year, "
        f"{calm.journeys} under an endless temperate sky"
    )
    print(f"  days some road was shut: {sim.days_roads_shut} of {args.days}")
    print(f"  caravan-days spent sitting out weather: {sim.days_waited:.0f}")
    print(f"  out of food through the year: {', '.join(sim.hungry_colonies()) or 'nobody'}")
    print(f"  out of food with no seasons: {', '.join(calm.hungry_colonies()) or 'nobody'}")

    tiers: dict[int, int] = {}
    for tile in sim.network.tiles.values():
        tiers[tile.tier] = tiers.get(tile.tier, 0) + 1
    names = {1: "foot path", 2: "dirt road", 3: "paved"}
    worn = ", ".join(f"{n} {names[t]}" for t, n in sorted(tiers.items()))
    print(f"\nroads: {worn}")

    if sim.log:
        print("\nlast few journeys:")
        for line in sim.log[-args.journeys :]:
            print("  " + line)


if __name__ == "__main__":
    main()
