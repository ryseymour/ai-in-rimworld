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
    ap.add_argument("--settlements", type=int, default=3)
    ap.add_argument("--days", type=int, default=150)
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

    founded = [colony.population for colony in sim.colonies]

    sim.run(args.days)
    control.run(args.days)
    unled.run(args.days)
    tame.run(args.days)

    print(render(sim.world, sim.network, wilds=sim.wilds))
    print()
    print(legend(sim.world, sim.network, sim.wilds))

    print(f"\n--- after {args.days} days, {sim.journeys} journeys ---\n")
    print(
        f"{'colony':<12}{'people':>8}{'food':>9}{'wood':>9}{'stone':>9}"
        f"{'cloth':>9}{'tools':>9}{'coin':>10}"
    )
    for colony in sim.colonies:
        row = "".join(f"{colony.storage.get(g):>9.0f}" for g in GOOD_NAMES)
        print(
            f"{colony.name:<12}{colony.population:>8.0f}{row}"
            f"{colony.purse.amount:>10.0f}"
        )

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

    print("\n--- the people ---\n")
    print(f"  {'colony':<12}{'founded':>9}{'now':>7}{'fed':>8}")
    for colony, was in zip(sim.colonies, founded):
        print(
            f"  {colony.name:<12}{was:>9.0f}{colony.population:>7.0f}"
            f"{colony.nourishment:>8.0%}"
        )
    print(f"\n  born: {sim.born:.0f}, starved: {sim.starved:.0f}, left: {sim.left:.0f}")
    # The claim population makes about trade, and the only one worth making:
    # not that traded worlds are bigger -- moving food around can leave the
    # colony that grew it with less to grow on -- but that nobody has to die
    # or walk out of one.
    print(
        f"  people lost with trade:  {sim.starved + sim.left:.0f}"
        f"  (without: {control.starved + control.left:.0f})"
    )
    print(f"  shrinking: {', '.join(sim.shrinking_colonies()) or 'nobody'}")
    print(f"  without trade: {', '.join(control.shrinking_colonies()) or 'nobody'}")

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
