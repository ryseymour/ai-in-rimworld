"""Generate a world, run it, and print what happened.

    python -m colonysim.demo --seed 23 --days 150
"""
from __future__ import annotations

import argparse

from .goods import GOOD_NAMES
from .render import legend, render
from .simulation import build_simulation


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a world and trade across it.")
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--width", type=int, default=90)
    ap.add_argument("--height", type=int, default=45)
    ap.add_argument("--settlements", type=int, default=6)
    ap.add_argument("--days", type=int, default=150)
    ap.add_argument("--journeys", type=int, default=6, help="journeys to print")
    args = ap.parse_args()

    sim = build_simulation(args.seed, args.settlements, args.width, args.height)
    control = build_simulation(args.seed, args.settlements, args.width, args.height)
    control.trade_enabled = False
    # The same world with the wolves and bears taken off it, so the cost of
    # the wild can be read straight off the difference.
    tame = build_simulation(
        args.seed, args.settlements, args.width, args.height, wildlife=False
    )

    sim.run(args.days)
    control.run(args.days)
    tame.run(args.days)

    print(render(sim.world, sim.network, wilds=sim.wilds))
    print()
    print(legend(sim.world, sim.network, sim.wilds))

    print(f"\n--- after {args.days} days, {sim.journeys} journeys ---\n")
    print(f"{'colony':<12}{'food':>9}{'wood':>9}{'stone':>9}{'cloth':>9}{'tools':>9}{'coin':>10}")
    for colony in sim.colonies:
        row = "".join(f"{colony.storage.get(g):>9.0f}" for g in GOOD_NAMES)
        print(f"{colony.name:<12}{row}{colony.purse.amount:>10.0f}")

    print("\nprice gap between the dearest and cheapest colony:")
    print(f"  {'good':<8}{'with trade':>12}{'without':>12}")
    for good in GOOD_NAMES:
        print(f"  {good:<8}{sim.price_spread(good):>12.2f}{control.price_spread(good):>12.2f}")

    hungry = sim.hungry_colonies()
    starved = control.hungry_colonies()
    print(f"\nout of food, with trade: {', '.join(hungry) or 'nobody'}")
    print(f"out of food, without:    {', '.join(starved) or 'nobody'}")

    print(f"\n--- the wild ---\n")
    print(f"  journeys made:      {sim.journeys}  (a tame world: {tame.journeys})")
    print(f"  met on the road:    {sim.meetings}")
    print(f"  raided:             {sim.raids}")
    print(f"  turned back:        {sim.journeys_turned_back}")
    lost = ", ".join(f"{q:.0f} {g}" for g, q in sorted(sim.lost.items()) if q >= 0.5)
    print(f"  taken by animals:   {lost or 'nothing'}")
    print(f"  paid to guards:     {sim.escort_wages:.0f} coin")

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
